# Minecraft runtime

* Software: vanilla, paper, purpur, spigot, fabric, forge, neoforge, quilt.
  Each family maps to its own image (`minecraft-paper-runtime`,
  `minecraft-fabric-runtime`, ...). Template = version + software.
* Resources (RAM/CPU/disk) become real `Memory` / `NanoCpus` limits and JVM
  `INIT_MEMORY` / `MAX_MEMORY`.
* Volume `/data/minecraft/{id}` holds `world*/ plugins/ mods/ config/ logs/
  server.properties`.
* `server.properties` has a form editor and a raw editor; both write the file in
  the volume and update the DB copy.
* Plugins (.jar) go to `plugins/`, mods to `mods/`; disabling renames to
  `*.jar.disabled`.
* Bedrock support provisions Geyser + Floodgate and publishes the UDP port.
* Console commands are written to the server process **stdin** through the
  Docker attach endpoint (`say`, `op`, `whitelist add`, `stop`, ...).
