import { eq } from "drizzle-orm";
import { db } from "@/db";
import { webProjects } from "@/db/schema";
import type { ServiceType } from "@/lib/paths";
import { BaseRuntimeProvider } from "./base";
import { WEB_TEMPLATES, webTemplate, type WebTemplateId } from "./templates";
import type { RuntimeTemplate, ServiceRecord } from "./types";

const INDEX_HTML = (name: string) => `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${name}</title>
    <link rel="stylesheet" href="/style.css" />
  </head>
  <body>
    <main>
      <h1>${name}</h1>
      <p>Deployed by Orbital on a dedicated web runtime container.</p>
    </main>
    <script src="/script.js"></script>
  </body>
</html>
`;

const STYLE_CSS = `:root { color-scheme: dark; }
body { margin: 0; display: grid; place-items: center; min-height: 100vh;
  font-family: ui-sans-serif, system-ui, sans-serif; background: #0b1020; color: #e5e7eb; }
h1 { font-size: 2.5rem; margin-bottom: .5rem; }
`;

const SCRIPT_JS = `console.log("Orbital web runtime ready");\n`;

const NODE_INDEX = (name: string) => `const http = require("node:http");
const port = process.env.PORT || 3000;
http
  .createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end("<h1>${name}</h1><p>Running in an Orbital web runtime container.</p>");
  })
  .listen(port, "0.0.0.0", () => console.log("listening on " + port));
`;

const startScript = (install: string, build: string, start: string) => `#!/bin/sh
set -e
cd /srv/app
echo "[orbital] web runtime starting"
if [ -f package.json ]; then
  if [ ! -d node_modules ] || [ package.json -nt node_modules ]; then
    echo "[orbital] install: ${install}"
    ${install}
  fi
fi
${build ? `echo "[orbital] build: ${build}"\n${build}` : ""}
echo "[orbital] start: ${start}"
exec ${start}
`;

export class WebRuntimeProvider extends BaseRuntimeProvider {
  readonly type: ServiceType = "web";

  private async record(serviceId: string) {
    return (
      await db.select().from(webProjects).where(eq(webProjects.serviceId, serviceId)).limit(1)
    )[0];
  }

  async scaffold(service: ServiceRecord): Promise<void> {
    const fsm = this.fs(service.id);
    const web = await this.record(service.id);
    const tplId = (web?.template ?? "static") as WebTemplateId;
    const meta = WEB_TEMPLATES.find((t) => t.id === tplId) ?? WEB_TEMPLATES[0];

    if (tplId === "static") {
      if (!(await fsm.exists("index.html"))) {
        await fsm.write("index.html", INDEX_HTML(service.name));
        await fsm.write("style.css", STYLE_CSS);
        await fsm.write("script.js", SCRIPT_JS);
      }
      return;
    }

    if (web?.source !== "github" && !(await fsm.exists("package.json"))) {
      await fsm.write(
        "package.json",
        JSON.stringify(
          {
            name: service.slug,
            version: "1.0.0",
            private: true,
            scripts: { start: "node index.js" },
          },
          null,
          2,
        ),
      );
      await fsm.write("index.js", NODE_INDEX(service.name));
    }

    await fsm.write(
      ".orbital/start.sh",
      startScript(
        web?.installCommand || meta.install || "npm install",
        web?.buildCommand || meta.build || "",
        web?.startCommand || meta.start || "npm run start",
      ),
    );
  }

  protected async template(service: ServiceRecord): Promise<RuntimeTemplate> {
    const web = await this.record(service.id);
    return webTemplate((web?.template ?? "static") as WebTemplateId);
  }

  protected async extraEnv(service: ServiceRecord): Promise<Record<string, string>> {
    const web = await this.record(service.id);
    return { NODE_ENV: "production", PORT: String(web?.port ?? 3000) };
  }

  protected async ports(service: ServiceRecord) {
    const web = await this.record(service.id);
    const tpl = webTemplate((web?.template ?? "static") as WebTemplateId);
    // Host port allocation is managed by the platform, not by the user.
    return [
      {
        containerPort: tpl.defaultPort ?? 3000,
        hostPort: web?.port ?? 3000,
        protocol: "tcp" as const,
      },
    ];
  }
}
