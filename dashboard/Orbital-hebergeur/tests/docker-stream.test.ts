import assert from "node:assert/strict";
import test from "node:test";

const { createFrameDecoder, createFramedLogDecoder, demuxDockerFrames, demuxDockerStream } = await import(
  "../src/lib/docker/engine"
);

function frame(type: 1 | 2, payload: string): Buffer {
  const body = Buffer.from(payload, "utf8");
  const header = Buffer.alloc(8);
  header[0] = type;
  header.writeUInt32BE(body.length, 4);
  return Buffer.concat([header, body]);
}

test("framed output is decoded and split per stream", () => {
  const buf = Buffer.concat([frame(1, "out\n"), frame(2, "err\n"), frame(1, "more\n")]);
  assert.deepEqual(demuxDockerFrames(buf), {
    combined: "out\nerr\nmore\n",
    stdout: "out\nmore\n",
    stderr: "err\n",
  });
});

test("plain output from a tty stream is passed through untouched", () => {
  const buf = Buffer.from("hello world\n", "utf8");
  assert.equal(demuxDockerStream(buf), "hello world\n");
});

test("payload bytes that look like a header are decoded by length", () => {
  const payload = "\u0001\u0000\u0000\u0000not a header\n";
  const buf = Buffer.concat([frame(1, "first\n"), frame(1, payload)]);
  assert.equal(demuxDockerStream(buf), `first\n${payload}`);
});

test("a frame split across chunks is reassembled instead of leaking its header", () => {
  const stream = Buffer.concat([frame(1, "a".repeat(9000)), frame(1, "tail\n")]);
  const decode = createFrameDecoder();
  let out = "";
  for (let offset = 0; offset < stream.length; offset += 1400) {
    out += decode(stream.subarray(offset, offset + 1400));
  }
  assert.equal(out, `${"a".repeat(9000)}tail\n`);
  assert.ok(!/[\u0000-\u0008]/.test(out), "no raw header bytes may reach the consumer");
});

test("a header split across chunks is buffered until complete", () => {
  const stream = frame(1, "split header\n");
  const decode = createFrameDecoder();
  assert.equal(decode(stream.subarray(0, 3)), "");
  assert.equal(decode(stream.subarray(3, 8)), "");
  assert.equal(decode(stream.subarray(8)), "split header\n");
});

test("multibyte characters cut in half between chunks survive", () => {
  const stream = frame(1, "héllo→ok\n");
  const cut = 8 + 2;
  const decode = createFrameDecoder();
  const first = decode(stream.subarray(0, cut));
  const second = decode(stream.subarray(cut));
  assert.equal(first + second, "héllo→ok\n");
});

test("live decoder keeps stdout and stderr apart", () => {
  const decode = createFramedLogDecoder();
  const pieces = decode(Buffer.concat([frame(1, "out\n"), frame(2, "err\n")]));
  assert.deepEqual(pieces, [
    { stream: "stdout", text: "out\n" },
    { stream: "stderr", text: "err\n" },
  ]);
});
