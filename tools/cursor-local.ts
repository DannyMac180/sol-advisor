import { createHash, randomUUID } from "node:crypto";
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join, parse, relative, resolve, sep } from "node:path";

const receiptName = ".sol-advisor-cursor-local.json";
const serverName = "sol-advisor";
const digestPattern = /^[0-9a-f]{64}$/;

type JsonObject = Record<string, unknown>;
type InstallOptions = {
  workspace: string;
  source?: string;
  cursorRoot?: string;
  bunPath?: string;
  platform?: NodeJS.Platform;
  beforeMcpCommit?: () => void;
};
type Receipt = {
  schema: 1;
  workspace: string;
  pluginDigest: string;
  projectEntry: JsonObject;
  createdMcpFile: boolean;
  createdCursorDirectory: boolean;
};
type FileSnapshot = { exists: false } | { exists: true; bytes: Buffer; mode: number };

function fail(message: string): never { throw new Error(message); }
function jsonBytes(bytes: Buffer, path: string): JsonObject {
  const value = JSON.parse(bytes.toString("utf8"));
  if (!value || Array.isArray(value) || typeof value !== "object") fail(`${path} must contain a JSON object`);
  return value as JsonObject;
}
function json(path: string): JsonObject { return jsonBytes(readFileSync(path), path); }
function same(a: unknown, b: unknown): boolean { return JSON.stringify(a) === JSON.stringify(b); }
function lstatExists(path: string): boolean {
  try { lstatSync(path); return true; } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}
function realDirectory(path: string, label: string): string {
  if (!existsSync(path) || lstatSync(path).isSymbolicLink() || !statSync(path).isDirectory()) fail(`${label} must be an existing non-symlink directory: ${path}`);
  return realpathSync(path);
}
function assertWithin(parent: string, child: string, label: string): void {
  const rel = relative(parent, child);
  if (!rel || rel === ".." || rel.startsWith(`..${sep}`) || resolve(parent, rel) !== child) fail(`${label} must be a descendant of ${parent}`);
}
function assertNoSymlinkComponents(path: string, label: string): void {
  const absolute = resolve(path);
  let current = parse(absolute).root;
  for (const part of relative(current, absolute).split(sep).filter(Boolean)) {
    current = join(current, part);
    if (lstatExists(current) && lstatSync(current).isSymbolicLink()) fail(`${label} has a symlink component: ${current}`);
  }
}
function atomicJson(path: string, value: unknown, mode = 0o600): void {
  const temp = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  try {
    writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, { mode });
    renameSync(temp, path);
  } finally {
    if (existsSync(temp)) rmSync(temp, { force: true });
  }
}
function snapshot(path: string): FileSnapshot {
  if (!lstatExists(path)) return { exists: false };
  if (lstatSync(path).isSymbolicLink() || !statSync(path).isFile()) fail(`workspace MCP config must be a non-symlink file: ${path}`);
  return { exists: true, bytes: readFileSync(path), mode: statSync(path).mode & 0o777 };
}
function assertUnchanged(path: string, original: FileSnapshot): void {
  const current = snapshot(path);
  if (current.exists !== original.exists || (current.exists && original.exists && !current.bytes.equals(original.bytes))) {
    fail(`workspace MCP config changed concurrently; refusing to overwrite: ${path}`);
  }
}
function commitMcp(path: string, original: FileSnapshot, value: JsonObject | null, before?: () => void): void {
  before?.();
  assertUnchanged(path, original);
  if (value === null) {
    if (original.exists) rmSync(path);
    return;
  }
  atomicJson(path, value, original.exists ? original.mode : 0o600);
}
function hashTree(root: string, excluded = new Set<string>()): string {
  const hash = createHash("sha256");
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const path = join(dir, entry.name);
      const rel = relative(root, path).split(sep).join("/");
      if (excluded.has(rel)) continue;
      if (entry.isSymbolicLink()) fail(`managed local plugin contains a symlink: ${path}`);
      if (entry.isDirectory()) { hash.update(`d\0${rel}\0`); walk(path); continue; }
      if (!entry.isFile()) fail(`managed local plugin contains an unsupported entry: ${path}`);
      hash.update(`f\0${rel}\0${statSync(path).mode & 0o777}\0`);
      hash.update(readFileSync(path));
      hash.update("\0");
    }
  };
  walk(root);
  return hash.digest("hex");
}
function resolveOptions(options: InstallOptions) {
  const platform = options.platform ?? process.platform;
  if (platform !== "darwin") fail("Cursor local compatibility installer currently supports macOS only");
  const source = realDirectory(options.source ?? resolve(import.meta.dir, "..", "plugins", "sol-advisor"), "plugin source");
  const workspace = realDirectory(options.workspace, "workspace");
  const cursorRoot = resolve(options.cursorRoot ?? join(homedir(), ".cursor"));
  const localRoot = join(cursorRoot, "plugins", "local");
  const target = join(localRoot, serverName);
  const quarantine = join(localRoot, `.${serverName}.removing`);
  const cursorDirectory = join(workspace, ".cursor");
  const data = join(cursorDirectory, "sol-advisor-dev-data");
  const bunPath = resolve(options.bunPath ?? Bun.which("bun") ?? fail("Bun is required to install the Cursor local adapter"));
  if (!existsSync(bunPath) || !statSync(bunPath).isFile() || (statSync(bunPath).mode & 0o111) === 0) fail(`Bun executable does not exist or is not executable: ${bunPath}`);
  return { source, workspace, cursorRoot, localRoot, target, quarantine, cursorDirectory, data, bunPath };
}
function projectEntry(paths: ReturnType<typeof resolveOptions>): JsonObject {
  return {
    command: paths.bunPath,
    args: [join(paths.target, "mcp", "server.ts")],
    cwd: paths.target,
    env: { PLUGIN_DATA: paths.data },
  };
}
function patchCopiedMcp(target: string): void {
  const path = join(target, "mcp.json");
  const doc = json(path);
  if (!doc.mcpServers || Array.isArray(doc.mcpServers) || typeof doc.mcpServers !== "object") fail("copied plugin has an invalid mcpServers object");
  doc.mcpServers = {};
  atomicJson(path, doc, 0o644);
}
function validateReceipt(root: string, paths: ReturnType<typeof resolveOptions>, expectedEntry: JsonObject): Receipt {
  const receiptPath = join(root, receiptName);
  if (!existsSync(receiptPath) || lstatSync(receiptPath).isSymbolicLink() || !statSync(receiptPath).isFile()) fail(`managed install receipt is missing or unsafe: ${receiptPath}`);
  const raw = json(receiptPath);
  const keys = Object.keys(raw).sort();
  const expectedKeys = ["createdCursorDirectory", "createdMcpFile", "pluginDigest", "projectEntry", "schema", "workspace"].sort();
  if (!same(keys, expectedKeys) || raw.schema !== 1 || raw.workspace !== paths.workspace ||
      typeof raw.pluginDigest !== "string" || !digestPattern.test(raw.pluginDigest) ||
      typeof raw.createdMcpFile !== "boolean" || typeof raw.createdCursorDirectory !== "boolean" ||
      !raw.projectEntry || Array.isArray(raw.projectEntry) || typeof raw.projectEntry !== "object" ||
      !same(raw.projectEntry, expectedEntry)) {
    fail("managed install receipt is invalid, changed, or belongs to another workspace");
  }
  const receipt = raw as unknown as Receipt;
  if (hashTree(root, new Set([receiptName])) !== receipt.pluginDigest) fail(`refusing to use changed local plugin: ${root}`);
  return receipt;
}
function readMcp(path: string): { original: FileSnapshot; mcp: JsonObject; servers: JsonObject; created: boolean } {
  const original = snapshot(path);
  const mcp = original.exists ? jsonBytes(original.bytes, path) : { mcpServers: {} };
  if (!mcp.mcpServers || Array.isArray(mcp.mcpServers) || typeof mcp.mcpServers !== "object") fail(`${path} must contain an mcpServers object`);
  return { original, mcp, servers: mcp.mcpServers as JsonObject, created: !original.exists };
}

export function installCursorLocal(options: InstallOptions): { target: string; workspaceMcp: string; data: string; recovered: boolean } {
  const paths = resolveOptions(options);
  if (lstatExists(paths.quarantine)) fail(`interrupted uninstall requires guarded uninstall recovery first: ${paths.quarantine}`);
  if (existsSync(paths.cursorDirectory) && (lstatSync(paths.cursorDirectory).isSymbolicLink() || !statSync(paths.cursorDirectory).isDirectory())) fail(`workspace .cursor must be a non-symlink directory: ${paths.cursorDirectory}`);
  const createdCursorDirectory = !existsSync(paths.cursorDirectory);
  const mcpPath = join(paths.cursorDirectory, "mcp.json");
  const mcpState = readMcp(mcpPath);
  const targetExisted = lstatExists(paths.target);
  if (!targetExisted && Object.hasOwn(mcpState.servers, serverName)) fail(`${mcpPath} already defines ${serverName}; refusing to overwrite it`);

  assertNoSymlinkComponents(paths.cursorRoot, "Cursor root");
  assertNoSymlinkComponents(paths.localRoot, "Cursor local-plugin root");
  assertNoSymlinkComponents(paths.data, "PLUGIN_DATA");
  mkdirSync(paths.localRoot, { recursive: true, mode: 0o700 });
  mkdirSync(paths.cursorDirectory, { recursive: true, mode: 0o700 });
  if (!existsSync(paths.data)) mkdirSync(paths.data, { mode: 0o700 });
  const dataReal = realDirectory(paths.data, "PLUGIN_DATA");
  assertWithin(paths.workspace, dataReal, "PLUGIN_DATA");
  if ((statSync(dataReal).mode & 0o077) !== 0) fail(`PLUGIN_DATA must be private (0700): ${dataReal}`);
  const entry = projectEntry({ ...paths, data: dataReal });

  let createdTarget = false;
  let recovered = false;
  const staging = join(paths.localRoot, `.${serverName}.${process.pid}.${randomUUID()}.tmp`);
  try {
    if (lstatExists(paths.target)) {
      if (lstatSync(paths.target).isSymbolicLink() || !statSync(paths.target).isDirectory()) fail(`existing Cursor local plugin is unsafe: ${paths.target}`);
      validateReceipt(paths.target, paths, entry);
      recovered = true;
    } else {
      cpSync(paths.source, staging, { recursive: true, errorOnExist: true, force: false, verbatimSymlinks: true });
      patchCopiedMcp(staging);
      const receipt: Receipt = {
        schema: 1,
        workspace: paths.workspace,
        pluginDigest: hashTree(staging),
        projectEntry: entry,
        createdMcpFile: mcpState.created,
        createdCursorDirectory,
      };
      atomicJson(join(staging, receiptName), receipt, 0o600);
      renameSync(staging, paths.target);
      createdTarget = true;
    }

    if (Object.hasOwn(mcpState.servers, serverName)) {
      if (!same(mcpState.servers[serverName], entry)) fail(`${mcpPath} already defines ${serverName}; refusing to overwrite it`);
      return { target: paths.target, workspaceMcp: mcpPath, data: dataReal, recovered };
    }
    mcpState.servers[serverName] = entry;
    commitMcp(mcpPath, mcpState.original, mcpState.mcp, options.beforeMcpCommit);
    return { target: paths.target, workspaceMcp: mcpPath, data: dataReal, recovered };
  } catch (error) {
    if (existsSync(staging)) rmSync(staging, { recursive: true, force: true });
    if (createdTarget && existsSync(paths.target)) rmSync(paths.target, { recursive: true, force: true });
    throw error;
  }
}

export function uninstallCursorLocal(options: InstallOptions): { removed: string; preservedData: string; recovered: boolean } {
  const paths = resolveOptions(options);
  assertNoSymlinkComponents(paths.cursorRoot, "Cursor root");
  assertNoSymlinkComponents(paths.localRoot, "Cursor local-plugin root");
  assertNoSymlinkComponents(paths.target, "managed Cursor plugin");
  assertNoSymlinkComponents(paths.quarantine, "uninstall quarantine");
  assertNoSymlinkComponents(paths.cursorDirectory, "workspace .cursor");
  assertNoSymlinkComponents(paths.data, "PLUGIN_DATA");
  if (lstatExists(paths.target) && lstatExists(paths.quarantine)) fail(`both managed target and uninstall quarantine exist; refusing recovery`);
  const recovered = !lstatExists(paths.target) && lstatExists(paths.quarantine);
  const active = recovered ? paths.quarantine : paths.target;
  if (!lstatExists(active) || lstatSync(active).isSymbolicLink() || !statSync(active).isDirectory()) fail(`managed Cursor local plugin is missing or unsafe: ${active}`);
  const dataReal = realDirectory(paths.data, "PLUGIN_DATA");
  assertWithin(paths.workspace, dataReal, "PLUGIN_DATA");
  if ((statSync(dataReal).mode & 0o077) !== 0) fail(`PLUGIN_DATA must be private (0700): ${dataReal}`);
  const expectedEntry = projectEntry({ ...paths, data: dataReal });
  const receipt = validateReceipt(active, paths, expectedEntry);

  const mcpPath = join(paths.cursorDirectory, "mcp.json");
  const mcpState = readMcp(mcpPath);
  const hasEntry = Object.hasOwn(mcpState.servers, serverName);
  if (hasEntry && !same(mcpState.servers[serverName], expectedEntry)) fail(`refusing to remove changed ${serverName} entry from ${mcpPath}`);
  if (!mcpState.original.exists && !receipt.createdMcpFile) fail(`workspace MCP config is missing; refusing to remove a plugin installed alongside a pre-existing config`);

  try {
    if (!recovered) { renameSync(paths.target, paths.quarantine); }
    if (hasEntry) delete mcpState.servers[serverName];
    if (hasEntry) {
      const onlyEmptyServers = Object.keys(mcpState.mcp).length === 1 && Object.keys(mcpState.servers).length === 0;
      commitMcp(mcpPath, mcpState.original, receipt.createdMcpFile && onlyEmptyServers ? null : mcpState.mcp, options.beforeMcpCommit);
    }
    rmSync(paths.quarantine, { recursive: true });
    return { removed: paths.target, preservedData: paths.data, recovered };
  } catch (error) {
    if (!lstatExists(paths.target) && lstatExists(paths.quarantine)) renameSync(paths.quarantine, paths.target);
    throw error;
  }
}

function usage(): never {
  fail("usage: bun tools/cursor-local.ts <install|uninstall> --workspace <absolute-or-relative-directory>");
}
function parseCli(): { action: "install" | "uninstall"; workspace: string } {
  const [action, ...args] = Bun.argv.slice(2);
  if (action !== "install" && action !== "uninstall") usage();
  const index = args.indexOf("--workspace");
  if (index < 0 || !args[index + 1] || args.length !== 2) usage();
  return { action, workspace: resolve(args[index + 1]) };
}

if (import.meta.main) {
  try {
    const { action, workspace } = parseCli();
    const result = action === "install" ? installCursorLocal({ workspace }) : uninstallCursorLocal({ workspace });
    console.log(JSON.stringify({ ok: true, action, ...result }, null, 2));
  } catch (error) {
    console.error(`ERROR: ${(error as Error).message}`);
    process.exit(1);
  }
}
