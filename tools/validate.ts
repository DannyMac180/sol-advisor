import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, realpathSync, chmodSync } from "node:fs";
import { basename, dirname, isAbsolute, join, normalize, relative, resolve, sep } from "node:path";
import { tmpdir } from "node:os";

const root = resolve(import.meta.dir, "..");
const plugin = join(root, "plugins", "sol-advisor");
const schemaUrl = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json";
const schemaSha256 = "0a4aad95ce337878ad38802ebf0daa3fde76abe3f65400c86bcbb1ec0b3ab883";
const mcpSchemaSha256 = "6539175bfcdf43085855183e86da40ea94b166547a72b47ae9a0a390516d3acb";
const pluginNamePattern = /^[a-z0-9](?:[a-z0-9.-]{0,62}[a-z0-9])?$/;
const skillNamePattern = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;
const allowed = new Set(["$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords", "extensions"]);
const authorAllowed = new Set(["name", "email", "url"]);
const errors: string[] = [];
const fail = (message: string) => errors.push(message);
const json = (path: string): any => JSON.parse(readFileSync(path, "utf8"));

function validateManifest(value: any, label: string): boolean {
  const before = errors.length;
  if (!value || Array.isArray(value) || typeof value !== "object") { fail(`${label}: manifest must be an object`); return false; }
  for (const key of Object.keys(value)) if (!allowed.has(key)) fail(`${label}: unknown top-level field ${key}`);
  if (value.$schema !== schemaUrl) fail(`${label}: $schema must be ${schemaUrl}`);
  if (typeof value.name !== "string" || !pluginNamePattern.test(value.name) || value.name.includes("--") || value.name.includes("..")) fail(`${label}: invalid name (must be 1-64 lowercase alphanumeric, period, or hyphen; no -- or ..)`);
  if (value.version !== undefined && (typeof value.version !== "string" || !/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(value.version))) fail(`${label}: version must be semver`);
  for (const key of ["description", "homepage", "repository", "license"])
    if (value[key] !== undefined && typeof value[key] !== "string") fail(`${label}: ${key} must be a string`);
  if (value.keywords !== undefined && (!Array.isArray(value.keywords) || value.keywords.some((x: unknown) => typeof x !== "string"))) fail(`${label}: keywords must contain only strings`);
  if (value.author !== undefined) {
    if (!value.author || Array.isArray(value.author) || typeof value.author !== "object") fail(`${label}: author must be an object`);
    else for (const [key, item] of Object.entries(value.author)) {
      if (!authorAllowed.has(key)) fail(`${label}: unknown author field ${key}`);
      if (typeof item !== "string") fail(`${label}: author.${key} must be a string`);
    }
  }
  if (value.extensions !== undefined) {
    if (!value.extensions || Array.isArray(value.extensions) || typeof value.extensions !== "object") fail(`${label}: extensions must be an object`);
    else for (const [key, item] of Object.entries(value.extensions)) if (!item || Array.isArray(item) || typeof item !== "object") fail(`${label}: extension ${key} must be an object`);
  }
  return errors.length === before;
}

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isSymbolicLink()) { fail(`${relative(root, path)}: symlinks are not portable`); continue; }
    if (entry.isDirectory()) out.push(...walk(path)); else if (entry.isFile()) out.push(path);
  }
  return out;
}

function exactCase(path: string, boundary: string): boolean {
  const absolute = resolve(path);
  const rel = relative(boundary, absolute);
  if (rel.startsWith("..") || isAbsolute(rel)) return false;
  let cursor = boundary;
  for (const part of rel.split(sep).filter(Boolean)) {
    const names = readdirSync(cursor);
    if (!names.includes(part)) return false;
    cursor = join(cursor, part);
  }
  return true;
}

function validateLinks(files: string[], boundary = root) {
  const link = /\[[^\]]*\]\(([^)]+)\)/g;
  for (const file of files.filter((p) => p.endsWith(".md"))) {
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(link)) {
      const raw = match[1]!.trim().replace(/^<|>$/g, "");
      if (!raw || raw.startsWith("#") || /^[a-z][a-z0-9+.-]*:/i.test(raw)) continue;
      const targetText = decodeURIComponent(raw.split("#", 1)[0]!);
      if (isAbsolute(targetText) || targetText.split(/[\\/]/).includes("..")) { fail(`${relative(boundary, file)}: non-contained link ${raw}`); continue; }
      const target = resolve(dirname(file), targetText);
      const rel = relative(boundary, target);
      if (rel.startsWith("..") || isAbsolute(rel)) fail(`${relative(boundary, file)}: link escapes package ${raw}`);
      else if (!existsSync(target)) fail(`${relative(boundary, file)}: broken link ${raw}`);
      else if (!exactCase(target, boundary)) fail(`${relative(boundary, file)}: link case mismatch ${raw}`);
    }
  }
}

function discoverSkills(skillsRoot: string): string[] {
  if (!existsSync(skillsRoot)) { fail(`${skillsRoot}: skills directory missing`); return []; }
  const found: string[] = [];
  for (const entry of readdirSync(skillsRoot, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.isSymbolicLink()) continue;
    const skill = join(skillsRoot, entry.name, "SKILL.md");
    if (existsSync(skill)) found.push(skill);
  }
  return found;
}

function validateSkills(skillsRoot: string) {
  const skillFiles = discoverSkills(skillsRoot);
  if (!skillFiles.length) fail(`${skillsRoot}: no immediate-child skills found`);
  for (const path of skillFiles) {
    const text = readFileSync(path, "utf8");
    const frontmatter = text.match(/^---\n([\s\S]*?)\n---\n/);
    if (!frontmatter) { fail(`${path}: missing YAML frontmatter`); continue; }
    const name = frontmatter[1]!.match(/^name:\s*["']?([^"'\n]+)["']?\s*$/m)?.[1]?.trim();
    if (!name || name !== basename(dirname(path))) fail(`${path}: frontmatter name must equal skill directory`);
    if (!name || !skillNamePattern.test(name) || name.includes("--")) fail(`${path}: invalid Agent Skills name`);
    const quoted = frontmatter[1]!.match(/^description:\s*["']([\s\S]*?)["']\s*$/m)?.[1];
    const plain = frontmatter[1]!.match(/^description:\s*([^\n]+)$/m)?.[1]?.trim();
    const description = quoted ?? plain?.replace(/^['"]|['"]$/g, "");
    if (!description || description.length > 1024) fail(`${path}: description must be 1-1024 characters`);
  }
}

function validateTagValue(tag: string, versions: string[], label: string) {
  if (!/^v\d+\.\d+\.\d+$/.test(tag)) { fail(`${label}: tag must be vX.Y.Z semver`); return; }
  const expected = tag.slice(1);
  for (const version of versions) if (version !== expected) fail(`${label}: ${tag} does not match version ${version}`);
}

function validateReleaseTag(tag: string) {
  validateRepository();
  const packageVersion = json(join(root, "package.json")).version;
  const standardVersion = json(join(plugin, "plugin.json")).version;
  const codexVersion = json(join(plugin, ".codex-plugin", "plugin.json")).version;
  validateTagValue(tag, [packageVersion, standardVersion, codexVersion], "release tag");
}

function expectErrors(label: string, action: () => void) {
  const count = errors.length;
  action();
  if (errors.length === count) fail(`${label}: expected invalid`);
  else errors.splice(count);
}

function validateFixtures() {
  const dir = join(root, "tools", "fixtures");
  const cases = json(join(dir, "cases.json"));
  for (const file of cases.positive) if (!validateManifest(json(join(dir, file)), `fixture ${file}`)) fail(`fixture ${file}: expected valid`);
  for (const file of cases.negative) expectErrors(`fixture ${file}`, () => { validateManifest(json(join(dir, file)), `fixture ${file}`); });
  for (const file of cases.positiveLinks) validateLinks([join(dir, file)], dir);
  for (const file of cases.negativeLinks) expectErrors(`fixture ${file}`, () => { validateLinks([join(dir, file)], dir); });
  validateSkills(join(dir, "skills", "valid"));
  expectErrors("nested SKILL.md fixture", () => { validateSkills(join(dir, "skills", "nested")); });
  expectErrors("skill name/directory mismatch fixture", () => { validateSkills(join(dir, "skills", "mismatch")); });
  for (const item of cases.releaseTags.positive) validateTagValue(item.tag, item.versions, `tag fixture ${item.tag}`);
  for (const item of cases.releaseTags.negative) expectErrors(`tag fixture ${item.tag}`, () => { validateTagValue(item.tag, item.versions, `tag fixture ${item.tag}`); });
}

function validateMcp(path: string) {
  let value:any; try { value=json(path); } catch { fail(`${path}: invalid JSON`); return; }
  const expectedSchema="https://agent-plugins.org/schemas/1.0.0/mcp.schema.json";
  if (!value || typeof value!=="object" || Array.isArray(value) || Object.keys(value).some(k=>!["$schema","mcpServers"].includes(k)) || value.$schema!==expectedSchema) { fail(`${path}: MCP root must contain exact $schema and mcpServers`); return; }
  const servers=value.mcpServers; if(!servers||typeof servers!=="object"||Array.isArray(servers)||!Object.keys(servers).length) fail(`${path}: mcpServers must be non-empty`);
  for(const [name,server] of Object.entries(servers??{}) as [string,any][]) {
    if(!pluginNamePattern.test(name)) fail(`${path}: invalid MCP server name ${name}`);
    if(!server||typeof server!=="object"||Array.isArray(server)||Object.keys(server).some(k=>!["type","command","args","cwd"].includes(k))) fail(`${path}: invalid MCP server ${name}`);
    else { if(server.type!=="stdio"||server.command!=="bun") fail(`${path}: server must be stdio using bun`); if(!Array.isArray(server.args)||server.args.length!==1||server.args[0]!=="${PLUGIN_ROOT}/mcp/server.ts") fail(`${path}: server args must use packaged runtime`); if(server.cwd!=="${PLUGIN_ROOT}") fail(`${path}: cwd must be PLUGIN_ROOT`); if("env" in server) fail(`${path}: reserved PLUGIN_DATA must be client-injected, not configured`); }
  }
}

function validatePackage(packageRoot: string, readme?: string) {
  const files = walk(packageRoot);
  const standard = json(join(packageRoot, "plugin.json"));
  const codex = json(join(packageRoot, ".codex-plugin", "plugin.json"));
  validateManifest(standard, `${relative(root, packageRoot) || "package"}/plugin.json`);
  if (standard.name !== codex.name) fail("standard/Codex manifest name mismatch");
  if (standard.version !== codex.version) fail("standard/Codex manifest version mismatch");
  validateSkills(join(packageRoot, "skills"));
  validateLinks([...(readme ? [readme] : []), ...files.filter((file) => file.endsWith(".md"))], packageRoot);
  if (!existsSync(join(packageRoot, "mcp.json"))) fail("mcp.json is required"); else validateMcp(join(packageRoot, "mcp.json"));
  if (!existsSync(join(packageRoot,"mcp","server.ts"))) fail("MCP runtime server is required");
}

function validateRepository() {
  const schemaPath = join(root, "tools", "schema", "agent-plugin-v1.schema.json");
  const digest = createHash("sha256").update(readFileSync(schemaPath)).digest("hex");
  if (digest !== schemaSha256) fail(`vendored schema digest mismatch: ${digest}`);
  const pin = readFileSync(join(root, "tools", "schema", "agent-plugin-v1.schema.sha256"), "utf8").trim();
  if (pin !== `${schemaSha256}  agent-plugin-v1.schema.json`) fail("schema checksum file mismatch");
  const mcpSchemaPath=join(root,"tools","schema","agent-plugin-v1-mcp.schema.json");
  const mcpDigest=createHash("sha256").update(readFileSync(mcpSchemaPath)).digest("hex");
  if(mcpDigest!==mcpSchemaSha256) fail(`vendored MCP schema digest mismatch: ${mcpDigest}`);
  const mcpPin=readFileSync(join(root,"tools","schema","agent-plugin-v1-mcp.schema.sha256"),"utf8").trim();
  if(mcpPin!==`${mcpSchemaSha256}  agent-plugin-v1-mcp.schema.json`) fail("MCP schema checksum file mismatch");
  validatePackage(plugin, join(root, "README.md"));
  validateFixtures();
}

async function run(command: string, args: string[], cwd = root): Promise<string> {
  const proc = Bun.spawn([command, ...args], { cwd, stdout: "pipe", stderr: "pipe" });
  const [stdout, stderr, code] = await Promise.all([new Response(proc.stdout).text(), new Response(proc.stderr).text(), proc.exited]);
  if (code !== 0) throw new Error(`${command} failed (${code}): ${stderr.trim()}`);
  return stdout;
}

async function release(checkOnly: boolean) {
  validateRepository();
  if (errors.length) return;
  const version = json(join(plugin, "plugin.json")).version;
  const dist = join(root, "dist");
  mkdirSync(dist, { recursive: true });
  const artifact = join(dist, `sol-advisor-${version}.tar.gz`);
  rmSync(artifact, { force: true }); rmSync(`${artifact}.sha256`, { force: true });
  let extracted = "";
  try {
    await run("tar", ["-czf", artifact, "--exclude=.DS_Store", "--exclude=*.test.ts", "-C", plugin, "."]);
    const listing = (await run("tar", ["-tzf", artifact])).split("\n").filter(Boolean);
    if (listing.some((entry) => /(^|\/)server\.test\.ts$/.test(entry))) fail("artifact contains MCP source tests");
    for (const entry of listing) {
      const clean = normalize(entry.replace(/^\.\//, ""));
      if (!clean || clean === ".") continue;
      if (isAbsolute(clean) || clean === ".." || clean.startsWith(`..${sep}`)) fail(`artifact path escapes root: ${entry}`);
      if (clean.startsWith("plugins/sol-advisor/")) fail(`artifact is not flattened: ${entry}`);
    }
    if (!listing.some((x) => x.replace(/^\.\//, "") === "plugin.json")) fail("artifact lacks root plugin.json");
    const verbose = await run("tar", ["-tvzf", artifact]);
    for (const line of verbose.split("\n").filter(Boolean)) if (/^[lh]/.test(line)) fail(`artifact contains link entry: ${line}`);
    if (!errors.length) {
      extracted = mkdtempSync(join(tmpdir(), "sol-advisor-release-check-"));
      await run("tar", ["-xzf", artifact, "-C", extracted]);
      validatePackage(extracted);
      let runtimeData=join(extracted,"runtime-data"), runtimeHome=join(extracted,"runtime-home"); mkdirSync(runtimeData,{recursive:true}); chmodSync(runtimeData,0o700); mkdirSync(runtimeHome,{recursive:true}); runtimeData=realpathSync(runtimeData); runtimeHome=realpathSync(runtimeHome);
      const runtimeWork=join(extracted,"runtime-work"); mkdirSync(runtimeWork,{recursive:true});
      const server=Bun.spawn(["bun",join(extracted,"mcp","server.ts")],{env:{...process.env,PLUGIN_DATA:runtimeData,HOME:runtimeHome},stdin:"pipe",stdout:"pipe",stderr:"pipe"});
      const reader=server.stdout.getReader(), decoder=new TextDecoder(); let rpcBuffer="", rpcId=0;
      const rpc=async(method:string,params?:unknown)=>{ const id=++rpcId; server.stdin.write(JSON.stringify({jsonrpc:"2.0",id,method,...(params===undefined?{}:{params})})+"\n"); while(true){ const newline=rpcBuffer.indexOf("\n"); if(newline>=0){const line=rpcBuffer.slice(0,newline);rpcBuffer=rpcBuffer.slice(newline+1);const value=JSON.parse(line);if(value.id===id)return value;} const next=await reader.read(); if(next.done)throw new Error("extracted MCP server ended early"); rpcBuffer+=decoder.decode(next.value,{stream:true}); }};
      const init=await rpc("initialize",{protocolVersion:"2025-03-26"}), listed=await rpc("tools/list");
      const call=async(name:string,args:unknown={})=>{const value=await rpc("tools/call",{name,arguments:args});if(value.error)throw new Error(value.error.message);return value.result.structuredContent;};
      const prefs={client:"codex",scope:"project",workspace:runtimeWork,orchestrator:{model:"inherit"},roles:{routine:{model:"gpt-5.6-terra",effort:"high"},high:{model:"gpt-5.6-terra",effort:"high"},advisor:{model:"gpt-5.6-sol",effort:"high",readonly:true}}};
      const missing=await call("get_setup_status"), saved=await call("save_preferences",prefs), preview=await call("render_client_adapter",{workspace:runtimeWork}), installed=await call("install_client_adapter",{workspace:runtimeWork,confirmationToken:preview.confirmationToken}), uninstallPreview=await call("uninstall_client_adapter",{}), removed=await call("uninstall_client_adapter",{confirmationToken:uninstallPreview.confirmationToken});
      server.stdin.end(); reader.releaseLock(); const runtimeErr=await new Response(server.stderr).text(), runtimeCode=await server.exited;
      if(runtimeCode!==0) fail(`extracted MCP server failed: ${runtimeErr}`); else if(init?.result?.serverInfo?.name!=="sol-advisor"||listed?.result?.tools?.length!==8||missing?.status!=="missing"||!saved?.saved||installed?.installed?.length!==3||removed?.removed?.length!==3) fail("extracted MCP server core-flow check failed");
    }
    const digest = createHash("sha256").update(readFileSync(artifact)).digest("hex");
    await Bun.write(`${artifact}.sha256`, `${digest}  ${basename(artifact)}\n`);
    if (!checkOnly) console.log(`release: ${relative(root, artifact)}\nsha256: ${digest}`);
  } finally {
    if (extracted) rmSync(extracted, { recursive: true, force: true });
    if (checkOnly) { rmSync(artifact, { force: true }); rmSync(`${artifact}.sha256`, { force: true }); }
  }
}

const mode = Bun.argv[2] ?? "validate";
if (mode === "release" || mode === "release-check") await release(mode === "release-check");
else if (mode === "validate") validateRepository();
else if (mode === "tag-check") {
  const tag = Bun.argv[3] ?? process.env.GITHUB_REF_NAME ?? "";
  validateReleaseTag(tag);
}
else fail(`unknown command: ${mode}`);
if (errors.length) { for (const error of errors) console.error(`FAIL: ${error}`); process.exit(1); }
console.log(`PASS: ${mode}`);
