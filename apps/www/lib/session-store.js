'use strict';

const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const session = require('express-session');

/** Site session lifetime: 3 weeks from login, not sliding. */
const SESSION_MAX_AGE_MS = 21 * 24 * 60 * 60 * 1000;
const COOKIE_NAME = 'synkrone.sid';

function safeSid(sid) {
    return String(sid || '').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 128);
}

class FileSessionStore extends session.Store {
    constructor(dir) {
        super();
        this.dir = dir;
        fs.mkdirSync(dir, { recursive: true });
    }

    file(sid) {
        return path.join(this.dir, `${safeSid(sid)}.json`);
    }

    get(sid, cb) {
        fsp.readFile(this.file(sid), 'utf8')
            .then((raw) => {
                const data = JSON.parse(raw);
                if (!data || Number(data.expires) <= Date.now()) {
                    this.destroy(sid, () => cb(null, null));
                    return;
                }
                cb(null, data.sess || null);
            })
            .catch((err) => {
                if (err && err.code === 'ENOENT') return cb(null, null);
                cb(err);
            });
    }

    set(sid, sess, cb) {
        const maxAge = Number(sess?.cookie?.maxAge);
        const expires = Date.now() + (Number.isFinite(maxAge) && maxAge > 0 ? maxAge : SESSION_MAX_AGE_MS);
        const payload = `${JSON.stringify({ sess, expires })}\n`;
        fsp.writeFile(this.file(sid), payload, 'utf8').then(() => cb(null), cb);
    }

    destroy(sid, cb) {
        fsp.unlink(this.file(sid)).then(() => cb(null), (err) => {
            if (err && err.code === 'ENOENT') return cb(null);
            cb(err);
        });
    }

    touch(sid, sess, cb) {
        this.set(sid, sess, cb);
    }
}

function createFileSessionStore(dir) {
    return new FileSessionStore(dir);
}

function sessionCookieOptions(isProd) {
    return {
        maxAge: SESSION_MAX_AGE_MS,
        httpOnly: true,
        sameSite: 'lax',
        secure: Boolean(isProd)
    };
}

module.exports = {
    FileSessionStore,
    SESSION_MAX_AGE_MS,
    COOKIE_NAME,
    createFileSessionStore,
    sessionCookieOptions,
    safeSid
};
