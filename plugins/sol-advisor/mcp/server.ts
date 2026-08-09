#!/usr/bin/env bun
import { createHash, randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { constants as fsConstants, existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync, copyFileSync, chmodSync, linkSync, statSync, openSync, fsyncSync, closeSync, readdirSync } from "node:fs";
import { homedir, platform } from "node:os";
import { basename, dirname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";

export const CONFIG_SCHEMA_VERSION = 1;
export const MANAGED_MARKER = "sol-advisor-managed:v1";
const previewPlans=new Map<string,{digest:string;expires:number;userToken?:string;used:boolean}>();
let transactionFaultForTests:((point:string)=>void)|undefined;
export function __setManifestWriteFaultForTests(fault:((point:string)=>void)|undefined){transactionFaultForTests=fault;}
export const CLIENTS = ["codex", "cursor", "vscode", "github-copilot", "kiro"] as const;
export type Client = typeof CLIENTS[number];
export type Scope = "project" | "user";
export type RoleName = "routine" | "high" | "advisor";
export type RolePreference = { model: string; effort?: string; readonly?: boolean };
export type Preferences = {
  schemaVersion: 1; client: Client; scope: Scope;
  orchestrator: { model: "inherit"; recommendation?: { model: string; effort?: string } };
  roles: { routine: RolePreference; high: RolePreference; advisor: RolePreference };
  fallbackPolicy: "fail-closed"; fallbacks: string[];
  appTaskLane?: { enabled: boolean; model: "gpt-5.6-luna"; effort: "max" };
  profileKey: string; workspace: string; createdAt: string; updatedAt: string; pluginVersion: string;
};
type ManagedFile = { profileKey: string; path: string; hash: string; backup?: string };
type Manifest = { schemaVersion: 1; files: ManagedFile[]; updatedAt: string };

const pluginRoot = resolve(import.meta.dir, "..");
let pinnedDataDir:{lexical:string;real:string;dev:number;ino:number}|undefined;
export function __resetDataPinForTests(){pinnedDataDir=undefined;}
const windowsAclCheck = String.raw`
$ErrorActionPreference = "Stop"
$target = [Environment]::GetEnvironmentVariable("SOL_ADVISOR_ACL_PATH", "Process")
$kind = [Environment]::GetEnvironmentVariable("SOL_ADVISOR_ACL_KIND", "Process")
if ($kind -eq "directory") {
  $security = [IO.Directory]::GetAccessControl($target)
} elseif ($kind -eq "file") {
  $security = [IO.File]::GetAccessControl($target)
} else {
  throw "Unsupported ACL object kind"
}
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowedOwners = @(
  $currentUser,
  "S-1-5-18",
  "S-1-5-32-544"
)
$owner = $security.GetOwner([Security.Principal.SecurityIdentifier]).Value
if ($allowedOwners -notcontains $owner) { Write-Output "unsafe-owner"; exit 0 }
$raw = [Security.AccessControl.RawSecurityDescriptor]::new($security.GetSecurityDescriptorBinaryForm(), 0)
if ($null -eq $raw.DiscretionaryAcl) { Write-Output "unsafe-null-dacl"; exit 0 }
$allowed = @(
  $currentUser,
  "S-1-5-18",
  "S-1-5-32-544",
  "S-1-3-0",
  "S-1-3-4"
)
foreach ($entry in $security.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
  if ($entry.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow) { continue }
  $sid = $entry.IdentityReference.Value
  if ($allowed -notcontains $sid) { Write-Output "unsafe-access"; exit 0 }
}
Write-Output "private"
`;
type WindowsAclKind="directory"|"file";
function windowsPowerShellPath(){
  const roots=[process.env.SystemRoot,process.env.WINDIR,process.env.SystemDrive?join(process.env.SystemDrive,"Windows"):undefined,join(parse(process.execPath).root,"Windows"),join(parse(homedir()).root,"Windows")]
    .filter((root):root is string=>typeof root==="string"&&isAbsolute(root));
  const seen=new Set<string>();
  for(const root of roots){
    const normalized=resolve(root),key=normalized.toLowerCase();if(seen.has(key))continue;seen.add(key);
    const candidate=join(normalized,"System32","WindowsPowerShell","v1.0","powershell.exe");
    if(existsSync(candidate)&&lstatSync(candidate).isFile()&&!lstatSync(candidate).isSymbolicLink())return candidate;
  }
  throw new Error("Windows PowerShell is unavailable");
}
function assertPrivateWindowsPath(path:string,label:string,kind:WindowsAclKind){
  const cacheKey=`${kind}:${path}`;if(activeWindowsAclChecks?.has(cacheKey))return;
  let result:string;
  try{
    result=execFileSync(windowsPowerShellPath(),["-NoLogo","-NoProfile","-NonInteractive","-Command",windowsAclCheck],{encoding:"utf8",env:{...process.env,SOL_ADVISOR_ACL_PATH:path,SOL_ADVISOR_ACL_KIND:kind},timeout:30000,windowsHide:true}).trim();
  }catch(error){
    const code=error&&typeof error==="object"&&"code" in error&&typeof error.code==="string"?error.code:"unknown";
    throw new Error(`${label} ACL could not be verified (${code})`);
  }
  if(result!=="private"){
    const reason=result==="unsafe-owner"?"owner is outside the approved Windows principals":result==="unsafe-null-dacl"?"null DACL grants unrestricted access":result==="unsafe-access"?"ACL contains an unapproved allow ACE":"Windows ACL verification returned an unexpected result";
    throw new Error(`${label} must be private (${reason})`);
  }
  activeWindowsAclChecks?.add(cacheKey);
}
function assertPrivateDirectory(path:string,label:string){
  if(platform()!=="win32"){
    if((statSync(path).mode&0o077)!==0)throw new Error(`${label} must be private (no group/world permission bits)`);
    return;
  }
  assertPrivateWindowsPath(path,label,"directory");
}
function assertPrivateFile(path:string,label:string){
  if(platform()!=="win32")return;
  const info=lstatSync(path);if(info.isSymbolicLink()||!info.isFile())throw new Error(`${label} must be a regular non-symlink file`);
  assertPrivateWindowsPath(path,label,"file");
}
function dataDir(): string {
  const raw=process.env.PLUGIN_DATA;
  if (!raw || !isAbsolute(raw)) throw new Error("PLUGIN_DATA must be an explicit absolute existing directory");
  const lexical=resolve(raw),filesystemRoot=resolve(parse(lexical).root),forbidden=new Set([filesystemRoot,realpathSync(homedir()),pluginRoot]);
  if(forbidden.has(lexical)) throw new Error("PLUGIN_DATA cannot be filesystem root, home, or plugin root");
  let cursor=filesystemRoot;for(const part of relative(filesystemRoot,lexical).split(sep).filter(Boolean)){cursor=join(cursor,part);if(existsSync(cursor)&&lstatSync(cursor).isSymbolicLink())throw new Error(`PLUGIN_DATA has symlink ancestor: ${cursor}`);}
  if (!existsSync(lexical) || !lstatSync(lexical).isDirectory() || lstatSync(lexical).isSymbolicLink()) throw new Error("PLUGIN_DATA must be an existing non-symlink directory");
  const actual=realpathSync(lexical), st=statSync(actual), pinned=pinnedDataDir;
  assertPrivateDirectory(actual,"PLUGIN_DATA");
  if(pinned&&(pinned.lexical!==lexical||pinned.real!==actual||pinned.dev!==st.dev||pinned.ino!==st.ino))throw new Error("PLUGIN_DATA identity changed during this server process");
  if(!pinned)pinnedDataDir={lexical,real:actual,dev:st.dev,ino:st.ino}; return actual;
}
function configPath() { return join(dataDir(), "config.json"); }
function manifestPath() { return join(dataDir(), "managed-files.json"); }
function backupDir(){const root=dataDir(),path=join(root,"backups");if(!existsSync(path))mkdirSync(path,{mode:0o700});const info=lstatSync(path);if(info.isSymbolicLink()||!info.isDirectory())throw new Error("PLUGIN_DATA backups must be a real directory");const actual=realpathSync(path),rel=relative(root,actual);if(rel!=="backups"||isAbsolute(rel)||rel.startsWith(".."))throw new Error("PLUGIN_DATA backups escapes the pinned data root");assertPrivateDirectory(actual,"PLUGIN_DATA backups");if(platform()==="win32")for(const entry of readdirSync(actual,{withFileTypes:true}))if(entry.name.endsWith(".bak"))assertPrivateFile(join(actual,entry.name),"PLUGIN_DATA backup");return actual;}
function sha(text: string | Uint8Array) { return createHash("sha256").update(text).digest("hex"); }
function syncFile(path:string){const fd=openSync(path,platform()==="win32"?"r+":"r");try{fsyncSync(fd);}finally{closeSync(fd);}}
function syncDir(path:string){const fd=openSync(path,platform()==="win32"?"r+":"r");try{fsyncSync(fd);}finally{closeSync(fd);}}
function copyPrivateBackup(source:string,destination:string,label:string){let created=false;try{copyFileSync(source,destination,fsConstants.COPYFILE_EXCL);created=true;chmodSync(destination,0o600);syncFile(destination);syncDir(dirname(destination));assertPrivateFile(destination,label);}catch(error){if(created&&existsSync(destination)){rmSync(destination,{force:true});syncDir(dirname(destination));}throw error;}}
function atomicWrite(path: string, text: string) {
  mkdirSync(dirname(path), { recursive: true });
  const temp = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  try { writeFileSync(temp, text, { encoding: "utf8", mode: 0o600, flag: "wx" }); chmodSync(temp,0o600); syncFile(temp); renameSync(temp, path); syncDir(dirname(path)); }
  catch(error){ if(existsSync(temp)) rmSync(temp,{force:true}); throw error; }
}
function readSensitiveText(path:string,label:string){assertPrivateFile(path,label);return readFileSync(path,"utf8");}
function readJson(path: string,label:string): unknown { return JSON.parse(readSensitiveText(path,label)); }
function configState(): { status: "missing"|"ready"|"schema-old"|"corrupt"; preferences?: Preferences; detail?: string } {
  if (!existsSync(configPath())) return { status: "missing" };
  try {
    const raw: any = readJson(configPath(),"PLUGIN_DATA config.json");
    if (!raw || typeof raw !== "object" || raw.schemaVersion !== CONFIG_SCHEMA_VERSION) return { status: "schema-old", detail: "Setup schema is absent or unsupported; rerun setup." };
    if(typeof raw.activeProfile!=="string"||!raw.profiles||typeof raw.profiles!=="object"||!raw.profiles[raw.activeProfile]) return {status:"corrupt",detail:"active profile is missing"};
    const active=raw.profiles[raw.activeProfile], errors = validatePreferences(active);
    if (errors.length) return { status: "corrupt", detail: errors.join("; ") };
    return { status: "ready", preferences: active as Preferences };
  } catch (error) { return { status: "corrupt", detail: String(error) }; }
}
function exactString(v: unknown, field: string, errors: string[]) {
  if (typeof v !== "string" || !v.trim() || v !== v.trim() || /[\r\n\0]/.test(v)) errors.push(`${field} must be an exact, non-empty client-native identifier`);
}
export function validatePreferences(value: any): string[] {
  const errors: string[] = [];
  if (!value || typeof value !== "object" || Array.isArray(value)) return ["preferences must be an object"];
  const unknown=(object:any,allowed:string[],label:string)=>{if(!object||typeof object!=="object"||Array.isArray(object))return;for(const key of Object.keys(object))if(!allowed.includes(key))errors.push(`${label} contains unknown field ${key}`);};
  unknown(value,["schemaVersion","client","scope","orchestrator","roles","fallbackPolicy","fallbacks","appTaskLane","profileKey","workspace","createdAt","updatedAt","pluginVersion"],"preferences");
  unknown(value.orchestrator,["model","recommendation"],"orchestrator"); unknown(value.orchestrator?.recommendation,["model","effort"],"orchestrator recommendation");
  unknown(value.roles,["routine","high","advisor"],"roles"); for(const role of ["routine","high","advisor"]) unknown(value.roles?.[role],["model","effort","readonly"],`role ${role}`);
  unknown(value.appTaskLane,["enabled","model","effort"],"appTaskLane");
  if (value.schemaVersion !== 1) errors.push("schemaVersion must be 1");
  if (!CLIENTS.includes(value.client)) errors.push("client is unsupported");
  if (!(value.scope === "project" || value.scope === "user")) errors.push("scope must be project or user");
  if (value.orchestrator?.model !== "inherit") errors.push("orchestrator must inherit the parent model and effort");
  if (value.fallbackPolicy !== "fail-closed" || !Array.isArray(value.fallbacks) || value.fallbacks.length !== 0) errors.push("fallbacks must be empty with fail-closed policy");
  for (const role of ["routine", "high", "advisor"] as RoleName[]) {
    const r = value.roles?.[role];
    if (!r || typeof r !== "object") { errors.push(`roles.${role} is required`); continue; }
    exactString(r.model, `roles.${role}.model`, errors);
    if (r.effort !== undefined) exactString(r.effort, `roles.${role}.effort`, errors);
  }
  if (value.roles?.advisor?.readonly !== true) errors.push("advisor readonly preference must be true");
  if(typeof value.profileKey!=="string"||!value.profileKey||typeof value.workspace!=="string"||!isAbsolute(value.workspace)) errors.push("profileKey and absolute workspace are required");
  if (["vscode", "github-copilot", "kiro"].includes(value.client)) {
    for (const role of ["routine", "high", "advisor"] as RoleName[]) if (value.roles?.[role]?.effort !== undefined) errors.push(`${value.client} cannot persist a per-agent effort claim for ${role}`);
  }
  if (value.appTaskLane !== undefined && (value.appTaskLane.enabled !== true || value.appTaskLane.model !== "gpt-5.6-luna" || value.appTaskLane.effort !== "max")) errors.push("appTaskLane is an explicit opt-in gpt-5.6-luna/max lane only");
  return errors;
}
function safeWorkspace(input: unknown): string {
  if (typeof input !== "string" || !isAbsolute(input)) throw new Error("workspace must be an explicit absolute path to an existing directory");
  const lexical = resolve(input);
  if (!existsSync(lexical) || !lstatSync(lexical).isDirectory() || lstatSync(lexical).isSymbolicLink()) throw new Error("workspace must be an existing, non-symlink directory");
  return realpathSync(lexical);
}
function destinationBase(client: Client, scope: Scope, workspace: string): string {
  if (scope === "project") return client === "codex" ? join(workspace,".codex","agents") : client === "cursor" ? join(workspace,".cursor","agents") : (client === "vscode" || client === "github-copilot") ? join(workspace,".github","agents") : join(workspace,".kiro","agents");
  const home = realpathSync(homedir());
  return client === "codex" ? join(home,".codex","agents") : client === "cursor" ? join(home,".cursor","agents") : (client === "vscode" || client === "github-copilot") ? join(home,".copilot","agents") : join(home,".kiro","agents");
}
function assertNoSymlinkPath(path: string, allowedRoot: string) {
  const rel = relative(allowedRoot, path);
  if (!rel || rel.startsWith("..") || isAbsolute(rel) || rel.split(sep).some(x => x === "..")) throw new Error("destination escapes the client allowlist");
  let cursor = allowedRoot;
  for (const part of rel.split(sep).slice(0,-1)) {
    cursor = join(cursor, part);
    if (existsSync(cursor) && lstatSync(cursor).isSymbolicLink()) throw new Error(`symlinked destination component refused: ${cursor}`);
  }
  if (existsSync(path) && lstatSync(path).isSymbolicLink()) throw new Error(`symlink destination refused: ${path}`);
}
function instructions(role: RoleName): string {
  if (role === "advisor") return "Review the architecture, specification, actual diff, and verification evidence. Remain behaviorally read-only. Return ship, fix-first, or rethink; never implement fixes.";
  if (role === "routine") return "Implement bounded, well-specified, mechanical work. Preserve the settled architecture, owned files, interfaces, and concurrent edits. Run requested checks and report evidence.";
  return "Implement complex, security-sensitive, algorithmic, debugging, or wide-blast-radius work within the settled architecture. Surface ambiguity, preserve concurrent edits, and report verification evidence.";
}
function filenames(client: Client): Record<RoleName,string> {
  const ext = client === "codex" ? ".toml" : client === "vscode" || client === "github-copilot" ? ".agent.md" : ".md";
  return { routine:`sol-advisor-routine${ext}`, high:`sol-advisor-high${ext}`, advisor:`sol-advisor-advisor${ext}` };
}
function renderOne(client: Client, role: RoleName, pref: RolePreference): string {
  const marker = client === "codex" ? `# ${MANAGED_MARKER}` : `<!-- ${MANAGED_MARKER} -->`;
  const body = instructions(role);
  if (client === "codex") return `${marker}\nname = "sol_advisor_${role}"\ndescription = "Sol Advisor ${role} role"\nmodel = ${JSON.stringify(pref.model)}\n${pref.effort ? `model_reasoning_effort = ${JSON.stringify(pref.effort)}\n` : ""}${role === "advisor" ? 'sandbox_mode = "read-only"\n' : ""}\ndeveloper_instructions = ${JSON.stringify(body)}\n`;
  if (client === "cursor") return `---\nname: sol-advisor-${role}\ndescription: Sol Advisor ${role} role\nmodel: ${JSON.stringify(pref.model+(pref.effort ? ` [effort=${pref.effort}]` : ""))}\n${role === "advisor" ? "readonly: true\n" : ""}---\n${marker}\n\n${body}\n`;
  return `---\nname: sol-advisor-${role}\ndescription: Sol Advisor ${role} role\nmodel: ${JSON.stringify(pref.model)}\n---\n${marker}\n\n${body}\n`;
}
export function renderAdapter(preferences: Preferences, workspaceInput: string) {
  const errors = validatePreferences(preferences); if (errors.length) throw new Error(errors.join("; "));
  const workspace = safeWorkspace(workspaceInput); if(workspace!==preferences.workspace) throw new Error("workspace does not match the active saved profile");
  const base = destinationBase(preferences.client, preferences.scope, workspace), names = filenames(preferences.client);
  const allowedRoot = preferences.scope === "project" ? workspace : realpathSync(homedir());
  const files = (["routine","high","advisor"] as RoleName[]).map(role => {
    const path = join(base,names[role]); assertNoSymlinkPath(path,allowedRoot);
    const content = renderOne(preferences.client,role,preferences.roles[role]);
    return { role,path,content,hash:sha(content) };
  });
  const warnings: string[] = [];
  if (preferences.client === "cursor") warnings.push("Cursor may fall back when a pinned model is unavailable or restricted. Sol Advisor never chooses that fallback and cannot detect or prevent host fallback.");
  if (["vscode","github-copilot"].includes(preferences.client)) warnings.push("This client adapter can pin a model only. Reasoning effort and parent cost tier remain client/session constraints, not per-agent guarantees.");
  if (preferences.client === "kiro") warnings.push("Kiro effort is session/per-model, not a per-agent binding.");
  if (preferences.client !== "codex") warnings.push("Advisor read-only is a behavioral/client request; OS-enforced isolation is not guaranteed unless the client exposes evidence.");
  const targetState=files.map(f=>({path:f.path,state:existsSync(f.path)?(lstatSync(f.path).isFile()&&!lstatSync(f.path).isSymbolicLink()?sha(readFileSync(f.path)):"unsafe"):"missing"}));
  const planDigest=sha(JSON.stringify({files:files.map(({path,content})=>({path,content})),targetState}));
  const nonce=randomUUID(), confirmationToken=`INSTALL ${nonce}`, userScopeConfirmationToken=preferences.scope === "user" ? `INSTALL USER ${nonce}` : undefined;
  previewPlans.set(confirmationToken,{digest:planDigest,expires:Date.now()+10*60_000,userToken:userScopeConfirmationToken,used:false});
  return { client:preferences.client,scope:preferences.scope,workspace,files,warnings,planDigest,targetState,expiresAt:new Date(Date.now()+10*60_000).toISOString(),confirmationToken,userScopeConfirmationToken,afterInstall:"Start a new chat or reload the client so native role discovery sees the adapter files." };
}
function loadManifest(): Manifest { if(!existsSync(manifestPath())) return {schemaVersion:1,files:[],updatedAt:new Date().toISOString()}; let x:any; try{x=readJson(manifestPath(),"PLUGIN_DATA managed-files.json");}catch(error){throw new Error(`managed-file manifest is corrupt: ${String(error)}`);} if(x?.schemaVersion!==1||!Array.isArray(x.files)) throw new Error("managed-file manifest schema is unsupported"); const paths=new Set<string>(); for(const file of x.files){if(!file||typeof file.profileKey!=="string"||typeof file.path!=="string"||!isAbsolute(file.path)||typeof file.hash!=="string"||!/^[a-f0-9]{64}$/.test(file.hash))throw new Error("managed-file manifest entry is invalid");if(paths.has(file.path))throw new Error(`managed-file manifest contains duplicate path ownership: ${file.path}`);paths.add(file.path);} return x; }
function requireExactManaged(path:string, hashValue:string) { const text=readFileSync(path,"utf8"); if(!text.includes(MANAGED_MARKER)||sha(text)!==hashValue) throw new Error(`managed file changed; refusing: ${path}`); }
type TxEntry={target:string;stage?:string;backup?:string;quarantine?:string;newHash:string;originalHash?:string;wasMissing?:boolean};
type TransactionJournal={schemaVersion:1;operation:"install"|"uninstall";phase:"prepared"|"targets-committed"|"manifest-committed";committed:number;entries:TxEntry[];manifestExisted:boolean;originalManifest:string;newManifest:string;profileKey:string};
function journalPath(){return join(dataDir(),"transaction.json");}
function writeJournal(tx:TransactionJournal){atomicWrite(journalPath(),JSON.stringify(tx,null,2)+"\n");}
function removeJournal(){if(existsSync(journalPath())){rmSync(journalPath(),{force:true});syncDir(dirname(journalPath()));}}
function currentHash(path:string){return existsSync(path)&&lstatSync(path).isFile()&&!lstatSync(path).isSymbolicLink()?sha(readFileSync(path)):undefined;}
function sensitiveCurrentHash(path:string,label:string){if(!existsSync(path))return undefined;assertPrivateFile(path,label);return currentHash(path);}
function removeExact(path:string,expected:string,label:string){if(currentHash(path)!==expected)throw new Error(`${label} hash mismatch: ${path}`);rmSync(path,{force:true});syncDir(dirname(path));}
function restoreManifest(tx:TransactionJournal){
  const actual=sensitiveCurrentHash(manifestPath(),"PLUGIN_DATA managed-files.json"),originalHash=sha(tx.originalManifest),newHash=sha(tx.newManifest);
  if(tx.manifestExisted){if(actual===originalHash)return;if(actual!==newHash)throw new Error("manifest changed during rollback");atomicWrite(manifestPath(),tx.originalManifest);}
  else if(existsSync(manifestPath())) { if(actual!==newHash) throw new Error("manifest changed during rollback"); rmSync(manifestPath(),{force:true}); syncDir(dirname(manifestPath())); }
}
function rollbackInstall(tx:TransactionJournal){
  for(let i=tx.entries.length-1;i>=0;i--){const e=tx.entries[i]!;if(e.stage&&existsSync(e.stage))removeExact(e.stage,e.newHash,"rollback stage");let actual=currentHash(e.target);if(actual===e.newHash){rmSync(e.target,{force:true});syncDir(dirname(e.target));actual=undefined;}if(e.wasMissing){if(actual!==undefined)throw new Error(`rollback refused changed target: ${e.target}`);}else if(e.quarantine&&existsSync(e.quarantine)){if(actual!==undefined)throw new Error(`rollback target reappeared: ${e.target}`);if(currentHash(e.quarantine)!==e.originalHash)throw new Error(`rollback quarantine hash mismatch: ${e.target}`);renameSync(e.quarantine,e.target);syncDir(dirname(e.target));}else if(actual!==e.originalHash)throw new Error(`rollback refused changed target: ${e.target}`);}
  restoreManifest(tx); removeJournal();
}
function rollbackUninstall(tx:TransactionJournal){
  for(let i=tx.entries.length-1;i>=0;i--){const e=tx.entries[i]!;if(e.quarantine&&existsSync(e.quarantine)){if(existsSync(e.target))throw new Error(`rollback target reappeared: ${e.target}`);renameSync(e.quarantine,e.target);syncDir(dirname(e.target));if(currentHash(e.target)!==e.originalHash)throw new Error(`rollback hash mismatch: ${e.target}`);}else if(currentHash(e.target)!==e.originalHash)throw new Error(`rollback refused changed target: ${e.target}`);}
  restoreManifest(tx); removeJournal();
}
function validateJournal(tx:any):asserts tx is TransactionJournal{
  const keys=(o:any)=>o&&typeof o==="object"&&!Array.isArray(o)?Object.keys(o):[];
  const top=["schemaVersion","operation","phase","committed","entries","manifestExisted","originalManifest","newManifest","profileKey"];
  if(!tx||keys(tx).some(k=>!top.includes(k))||tx.schemaVersion!==1||!["install","uninstall"].includes(tx.operation)||!["prepared","targets-committed","manifest-committed"].includes(tx.phase)||!Number.isInteger(tx.committed)||!Array.isArray(tx.entries)||tx.committed<0||tx.committed>tx.entries.length||typeof tx.manifestExisted!=="boolean"||typeof tx.originalManifest!=="string"||typeof tx.newManifest!=="string"||typeof tx.profileKey!=="string")throw new Error("transaction journal schema is invalid");
  const state=configState();if(state.status!=="ready"||state.preferences!.profileKey!==tx.profileKey)throw new Error("transaction journal does not match the active profile");
  const expected=new Set(renderAdapter(state.preferences!,state.preferences!.workspace).files.map(f=>f.path)),backupRoot=join(dataDir(),"backups"),entryKeys=["target","stage","backup","quarantine","newHash","originalHash","wasMissing"];
  const journalTargets=new Set(tx.entries.map((e:any)=>e?.target));if(tx.entries.length!==expected.size||journalTargets.size!==expected.size||[...expected].some(path=>!journalTargets.has(path)))throw new Error("transaction journal target set is incomplete or duplicated");
  const validSibling=(candidate:any,target:string,suffix:string)=>{if(typeof candidate!=="string"||dirname(candidate)!==dirname(target))return false;const name=basename(candidate),prefix=`.${basename(target)}.`,tail=`.${suffix}`;return name.startsWith(prefix)&&name.endsWith(tail)&&/^[0-9a-f-]{36}$/.test(name.slice(prefix.length,-tail.length));};
  for(const e of tx.entries){
    if(!e||keys(e).some(k=>!entryKeys.includes(k))||typeof e.target!=="string"||!expected.has(e.target)||typeof e.newHash!=="string"||(tx.operation==="install"&&!/^[a-f0-9]{64}$/.test(e.newHash))||(e.originalHash!==undefined&&!/^[a-f0-9]{64}$/.test(e.originalHash))||(e.wasMissing!==undefined&&typeof e.wasMissing!=="boolean"))throw new Error("transaction journal entry is invalid");
    if(e.stage!==undefined&&!validSibling(e.stage,e.target,"stage"))throw new Error("transaction stage path is invalid");
    if(e.quarantine!==undefined&&!validSibling(e.quarantine,e.target,"quarantine"))throw new Error("transaction quarantine path is invalid");
    if(e.backup!==undefined&&(typeof e.backup!=="string"||dirname(e.backup)!==backupRoot))throw new Error("transaction backup path is invalid");
  }
}
function recoverTransaction(){
  if(!existsSync(journalPath()))return;let tx:TransactionJournal;try{tx=readJson(journalPath(),"PLUGIN_DATA transaction.json") as TransactionJournal;}catch(error){throw new Error(`transaction journal is corrupt or unsafe: ${String(error)}; manual recovery required`);}
  validateJournal(tx);
  if(tx.phase==="manifest-committed"){for(const e of tx.entries){if(e.stage&&existsSync(e.stage))removeExact(e.stage,e.newHash,"recovery stage");if(e.quarantine&&existsSync(e.quarantine))removeExact(e.quarantine,e.originalHash!,"recovery quarantine");}removeJournal();return;}
  if(tx.operation==="install")rollbackInstall(tx);else if(tx.operation==="uninstall")rollbackUninstall(tx);else throw new Error("unknown transaction operation");
}
function installAdapter(args:any) {
  const state=configState(); if(state.status!=="ready") throw new Error(`setup is ${state.status}; run the parent-chat setup interview first`);
  rejectUnknown(args,["workspace","confirmationToken","userScopeConfirmationToken"],"install");
  for(const key of ["workspace","confirmationToken","userScopeConfirmationToken"]) if(typeof args[key]==="string"&&/[\r\n\0]/.test(args[key])) throw new Error(`${key} contains control characters`);
  const preview=renderAdapter(state.preferences!,args.workspace), plan=previewPlans.get(args.confirmationToken);
  if(!plan||plan.used||plan.expires<Date.now()||plan.digest!==preview.planDigest) throw new Error("installation requires the exact unexpired one-time preview confirmation token and unchanged target state");
  if(preview.scope==="user"&&args.userScopeConfirmationToken!==plan.userToken) throw new Error("user-scope installation requires the separate exact user-scope token"); plan.used=true;
  const manifest=loadManifest(), previous=new Map(manifest.files.map(f=>[f.path,f]));
  for(const f of preview.files){const known=previous.get(f.path);if(known&&known.profileKey!==state.preferences!.profileKey)throw new Error(`adapter path is owned by a different profile; explicit uninstall required: ${f.path}`);if(existsSync(f.path)){if(!known)throw new Error(`unmanaged/conflicting file refused: ${f.path}`);requireExactManaged(f.path,known.hash);}}
  const originalManifest=existsSync(manifestPath())?readSensitiveText(manifestPath(),"PLUGIN_DATA managed-files.json"):"", targetState=new Map(preview.targetState.map((x:any)=>[x.path,x.state]));
  const entries:TxEntry[]=[],installed:ManagedFile[]=[];
  for(const f of preview.files){const expected=targetState.get(f.path),wasMissing=expected==="missing",backup=wasMissing?undefined:join(dataDir(),"backups",`${Date.now()}-${randomUUID()}-${basename(f.path)}-${String(expected).slice(0,12)}.bak`),stage=join(dirname(f.path),`.${basename(f.path)}.${randomUUID()}.stage`),quarantine=wasMissing?undefined:join(dirname(f.path),`.${basename(f.path)}.${randomUUID()}.quarantine`);entries.push({target:f.path,stage,backup,quarantine,newHash:f.hash,originalHash:wasMissing?undefined:String(expected),wasMissing});installed.push({profileKey:state.preferences!.profileKey,path:f.path,hash:f.hash,backup});}
  const retained=manifest.files.filter(f=>f.profileKey!==state.preferences!.profileKey),newManifest=JSON.stringify({schemaVersion:1,files:[...retained,...installed],updatedAt:new Date().toISOString()},null,2)+"\n";
  const tx:TransactionJournal={schemaVersion:1,operation:"install",phase:"prepared",committed:0,entries,manifestExisted:existsSync(manifestPath()),originalManifest,newManifest,profileKey:state.preferences!.profileKey};writeJournal(tx);
  try{
    for(const e of entries){mkdirSync(dirname(e.target),{recursive:true});if(e.backup){const privateBackups=backupDir();if(dirname(e.backup)!==privateBackups)throw new Error("backup destination escaped private backup directory");copyPrivateBackup(e.target,e.backup,"PLUGIN_DATA adapter backup");if(currentHash(e.backup)!==e.originalHash)throw new Error(`backup hash mismatch: ${e.target}`);}writeFileSync(e.stage!,preview.files.find((f:any)=>f.path===e.target)!.content,{encoding:"utf8",mode:0o600,flag:"wx"});chmodSync(e.stage!,0o600);syncFile(e.stage!);syncDir(dirname(e.stage!));}
    transactionFaultForTests?.("install-before-targets");
    for(let i=0;i<entries.length;i++){const e=entries[i]!;assertNoSymlinkPath(e.target,state.preferences!.scope==="project"?state.preferences!.workspace:realpathSync(homedir()));const actual=currentHash(e.target);if(e.wasMissing){if(actual!==undefined||existsSync(e.target))throw new Error(`target appeared after preview: ${e.target}`);}else{if(actual!==e.originalHash)throw new Error(`managed target changed after preview: ${e.target}`);const before=lstatSync(e.target);transactionFaultForTests?.(`install-before-quarantine-${i+1}`);if(existsSync(e.quarantine!))throw new Error(`install quarantine conflict: ${e.quarantine}`);renameSync(e.target,e.quarantine!);syncDir(dirname(e.target));const quarantined=lstatSync(e.quarantine!);if(quarantined.isSymbolicLink()||!quarantined.isFile()||quarantined.dev!==before.dev||quarantined.ino!==before.ino||currentHash(e.quarantine!)!==e.originalHash){if(!existsSync(e.target)){renameSync(e.quarantine!,e.target);syncDir(dirname(e.target));}throw new Error(`install quarantine identity/hash mismatch: ${e.target}`);}}linkSync(e.stage!,e.target);rmSync(e.stage!,{force:true});syncDir(dirname(e.target));if(currentHash(e.target)!==e.newHash)throw new Error(`committed target hash mismatch: ${e.target}`);tx.committed=i+1;tx.phase="targets-committed";writeJournal(tx);transactionFaultForTests?.(`install-target-${i+1}`);}
    atomicWrite(manifestPath(),newManifest);transactionFaultForTests?.("install-manifest-commit");tx.phase="manifest-committed";writeJournal(tx);transactionFaultForTests?.("install-journal-commit");for(const e of entries)if(e.quarantine&&existsSync(e.quarantine))removeExact(e.quarantine,e.originalHash!,"committed quarantine");removeJournal();
  }catch(error){if((error instanceof Error&&error.message==="__SIMULATED_CRASH__")||tx.phase==="manifest-committed")throw error;try{rollbackInstall(tx);}catch(rollback){throw new Error(`${String(error)}; rollback incomplete: ${String(rollback)}`);}throw error;}
  return {installed:installed.map(x=>x.path),backups:installed.flatMap(x=>x.backup?[x.backup]:[]),guidance:preview.afterInstall};
}
function uninstallAdapter(args:any) {
  const state=configState(); if(state.status!=="ready") throw new Error(`setup is ${state.status}`);const manifest=loadManifest(),selected=manifest.files.filter(f=>f.profileKey===state.preferences!.profileKey);if(!selected.length)return {removed:[]};
  const expected=new Set(renderAdapter(state.preferences!,state.preferences!.workspace).files.map(f=>f.path));if(selected.some(f=>!expected.has(f.path))||selected.length!==expected.size)throw new Error("managed-file manifest destinations do not match the active client allowlist");
  const token=`UNINSTALL ${sha(JSON.stringify(selected.map(f=>({path:f.path,hash:f.hash}))))}`;if(args.confirmationToken!==token)return {requiresConfirmation:true,confirmationToken:token,files:selected.map(f=>f.path)};
  for(const f of selected)requireExactManaged(f.path,f.hash);
  const originalManifest=readSensitiveText(manifestPath(),"PLUGIN_DATA managed-files.json"),newManifest=JSON.stringify({schemaVersion:1,files:manifest.files.filter(f=>f.profileKey!==state.preferences!.profileKey),updatedAt:new Date().toISOString()},null,2)+"\n";
  const entries:TxEntry[]=selected.map(f=>({target:f.path,quarantine:join(dirname(f.path),`.${basename(f.path)}.${randomUUID()}.quarantine`),newHash:"",originalHash:f.hash}));const tx:TransactionJournal={schemaVersion:1,operation:"uninstall",phase:"prepared",committed:0,entries,manifestExisted:true,originalManifest,newManifest,profileKey:state.preferences!.profileKey};writeJournal(tx);
  try{for(let i=0;i<entries.length;i++){const e=entries[i]!;assertNoSymlinkPath(e.target,state.preferences!.scope==="project"?state.preferences!.workspace:realpathSync(homedir()));if(currentHash(e.target)!==e.originalHash)throw new Error(`managed file changed before uninstall commit: ${e.target}`);const before=lstatSync(e.target);transactionFaultForTests?.(`uninstall-before-quarantine-${i+1}`);if(existsSync(e.quarantine!))throw new Error(`quarantine conflict: ${e.quarantine}`);renameSync(e.target,e.quarantine!);syncDir(dirname(e.target));const quarantined=lstatSync(e.quarantine!);if(quarantined.isSymbolicLink()||!quarantined.isFile()||quarantined.dev!==before.dev||quarantined.ino!==before.ino||currentHash(e.quarantine!)!==e.originalHash){if(!existsSync(e.target)){renameSync(e.quarantine!,e.target);syncDir(dirname(e.target));}throw new Error(`uninstall quarantine identity/hash mismatch: ${e.target}`);}tx.committed=i+1;tx.phase="targets-committed";writeJournal(tx);transactionFaultForTests?.(`uninstall-target-${i+1}`);}atomicWrite(manifestPath(),newManifest);transactionFaultForTests?.("uninstall-manifest-commit");tx.phase="manifest-committed";writeJournal(tx);transactionFaultForTests?.("uninstall-journal-commit");for(const e of entries)if(e.quarantine&&existsSync(e.quarantine))removeExact(e.quarantine,e.originalHash!,"committed quarantine");removeJournal();}
  catch(error){if((error instanceof Error&&error.message==="__SIMULATED_CRASH__")||tx.phase==="manifest-committed")throw error;try{rollbackUninstall(tx);}catch(rollback){throw new Error(`${String(error)}; rollback incomplete: ${String(rollback)}`);}throw error;}
  return {removed:selected.map(f=>f.path),guidance:"Reload the client or start a new chat."};
}
function assertSafeInput(value:any, path="input") {
  const forbidden=/(secret|token|password|api.?key|credential|private.?key)/i;
  if (value && typeof value === "object") for (const [key,item] of Object.entries(value)) { if(forbidden.test(key)) throw new Error(`forbidden secret-like field: ${path}.${key}`); assertSafeInput(item,`${path}.${key}`); }
  if (typeof value === "string" && /[\r\n\0]/.test(value)) throw new Error(`${path} contains control characters`);
}
function rejectUnknown(value:any, allowed:string[], label:string){ for(const key of Object.keys(value??{})) if(!allowed.includes(key)) throw new Error(`unknown ${label} field: ${key}`); }
function savePreferences(args:any) {
  assertSafeInput(args); rejectUnknown(args,["client","scope","workspace","orchestrator","roles","appTaskLane"],"preference"); rejectUnknown(args.orchestrator,["model","recommendation"],"orchestrator");
  for(const name of ["routine","high","advisor"] as RoleName[]) rejectUnknown(args.roles?.[name],["model","effort","readonly"],`role ${name}`);
  const now=new Date().toISOString(), existing=configState(), workspace=safeWorkspace(args.workspace);
  const profileKey=`${args.client}:${args.scope}:${workspace}`;
  const candidate:any={schemaVersion:1,client:args.client,scope:args.scope,orchestrator:{model:"inherit",...(args.orchestrator?.recommendation?{recommendation:{model:args.orchestrator.recommendation.model,...(args.orchestrator.recommendation.effort!==undefined?{effort:args.orchestrator.recommendation.effort}:{})}}:{})},roles:{routine:{model:args.roles?.routine?.model,...(args.roles?.routine?.effort!==undefined?{effort:args.roles.routine.effort}:{}),...(args.roles?.routine?.readonly!==undefined?{readonly:args.roles.routine.readonly}:{})},high:{model:args.roles?.high?.model,...(args.roles?.high?.effort!==undefined?{effort:args.roles.high.effort}:{}),...(args.roles?.high?.readonly!==undefined?{readonly:args.roles.high.readonly}:{})},advisor:{model:args.roles?.advisor?.model,...(args.roles?.advisor?.effort!==undefined?{effort:args.roles.advisor.effort}:{}),readonly:true}},fallbackPolicy:"fail-closed",fallbacks:[],...(args.appTaskLane?.enabled===true?{appTaskLane:{enabled:true,model:"gpt-5.6-luna",effort:"max"}}:{}),profileKey,workspace,createdAt:existing.preferences?.profileKey===profileKey?existing.preferences.createdAt:now,updatedAt:now,pluginVersion:"0.5.0"};
  const errors=validatePreferences(candidate); if(errors.length) throw new Error(errors.join("; "));
  if(existsSync(configPath())) { assertPrivateFile(configPath(),"PLUGIN_DATA config.json");const privateBackups=backupDir(),backup=join(privateBackups,`${Date.now()}-config.json.bak`);if(dirname(backup)!==privateBackups)throw new Error("config backup destination changed");copyPrivateBackup(configPath(),backup,"PLUGIN_DATA configuration backup"); }
  let profiles:Record<string,Preferences>={}; try { const old:any=readJson(configPath(),"PLUGIN_DATA config.json"); if(old?.schemaVersion===1&&old.profiles&&typeof old.profiles==="object") profiles=old.profiles; } catch {}
  profiles[profileKey]=candidate; atomicWrite(configPath(),JSON.stringify({schemaVersion:1,activeProfile:profileKey,profiles},null,2)+"\n"); return {saved:true,profileKey,preferences:candidate};
}
function resetConfiguration(args:any) { const live=loadManifest().files; if(live.length) throw new Error("reset refused while managed adapter files are installed; uninstall them first"); const token="RESET SOL ADVISOR CONFIGURATION"; if(args.confirmationToken!==token) return {requiresConfirmation:true,confirmationToken:token}; for(const path of [configPath(),manifestPath(),join(dataDir(),"backups")]) if(existsSync(path)) rmSync(path,{recursive:true,force:true}); previewPlans.clear(); return {reset:true,purged:true}; }
const objectSchema=(properties:Record<string,unknown>={},required:string[]=[])=>({type:"object",properties,required,additionalProperties:false});
const str={type:"string"};
const roleSchema={type:"object",properties:{model:str,effort:str,readonly:{type:"boolean"}},required:["model"],additionalProperties:false};
export const tools = [
  {name:"get_setup_status",description:"Report missing, ready, schema-old, or corrupt setup state",inputSchema:objectSchema()},
  {name:"get_preferences",description:"Read non-secret logical preferences",inputSchema:objectSchema()},
  {name:"save_preferences",description:"Validate and atomically save interview choices",inputSchema:objectSchema({client:{type:"string",enum:CLIENTS},scope:{type:"string",enum:["project","user"]},workspace:str,orchestrator:{type:"object",properties:{model:{const:"inherit"},recommendation:{type:"object",properties:{model:str,effort:str},required:["model"],additionalProperties:false}},required:["model"],additionalProperties:false},roles:{type:"object",properties:{routine:roleSchema,high:roleSchema,advisor:roleSchema},required:["routine","high","advisor"],additionalProperties:false},appTaskLane:{type:"object",properties:{enabled:{const:true}},required:["enabled"],additionalProperties:false}},["client","scope","workspace","orchestrator","roles"])},
  {name:"render_client_adapter",description:"Preview exact allowlisted native adapter paths and contents",inputSchema:objectSchema({workspace:str},["workspace"])},
  {name:"install_client_adapter",description:"Install only the confirmed exact preview",inputSchema:objectSchema({workspace:str,confirmationToken:str,userScopeConfirmationToken:str},["workspace","confirmationToken"])},
  {name:"uninstall_client_adapter",description:"Preview or confirm removal of exact managed files",inputSchema:objectSchema({confirmationToken:str})},
  {name:"validate_configuration",description:"Validate setup and optionally renderability",inputSchema:objectSchema({workspace:str})},
  {name:"reset_configuration",description:"Reset logical configuration with exact confirmation",inputSchema:objectSchema({confirmationToken:str})}
];
let activeWindowsAclChecks:Set<string>|undefined;
export async function callTool(name:string,args:any={}) {
 const previousAclChecks=activeWindowsAclChecks;if(platform()==="win32")activeWindowsAclChecks=new Set();
 try{
  const allowed:Record<string,string[]>={get_setup_status:[],get_preferences:[],save_preferences:["client","scope","workspace","orchestrator","roles","appTaskLane"],render_client_adapter:["workspace"],install_client_adapter:["workspace","confirmationToken","userScopeConfirmationToken"],uninstall_client_adapter:["confirmationToken"],validate_configuration:["workspace"],reset_configuration:["confirmationToken"]};
  if(!(name in allowed)) throw new Error(`unknown tool: ${name}`); rejectUnknown(args,allowed[name]!,name); recoverTransaction();
  if(name!=="save_preferences") for(const [key,value] of Object.entries(args)) if(typeof value==="string"&&/[\r\n\0]/.test(value)) throw new Error(`${key} contains control characters`);
  if(name==="get_setup_status") return configState();
  if(name==="get_preferences") { const s=configState(); if(s.status!=="ready") throw new Error(`setup is ${s.status}`); return s.preferences; }
  if(name==="save_preferences") return savePreferences(args);
  if(name==="render_client_adapter") { const s=configState(); if(s.status!=="ready") throw new Error(`setup is ${s.status}`); return renderAdapter(s.preferences!,args.workspace); }
  if(name==="install_client_adapter") return installAdapter(args);
  if(name==="uninstall_client_adapter") return uninstallAdapter(args);
  if(name==="validate_configuration") { const s=configState(); return {status:s.status,valid:s.status==="ready",detail:s.detail,...(s.status==="ready"&&args.workspace?{preview:renderAdapter(s.preferences!,args.workspace)}:{})}; }
  if(name==="reset_configuration") return resetConfiguration(args);
  throw new Error(`unknown tool: ${name}`);
 }finally{activeWindowsAclChecks=previousAclChecks;}
}
function response(id:unknown,result?:unknown,error?:unknown,code=-32000){ return error?{jsonrpc:"2.0",id,error:{code,message:error instanceof Error?error.message:String(error)}}:{jsonrpc:"2.0",id,result}; }
export async function handle(message:any){
  if(!message||message.jsonrpc!=="2.0"||typeof message.method!=="string"||("id" in (message??{}) && !["string","number"].includes(typeof message.id) && message.id!==null)) return response(message?.id??null,undefined,new Error("invalid JSON-RPC 2.0 request"),-32600);
  const notification=!("id" in message);
  if(message.method==="notifications/initialized") return null;
  if(notification) return null;
  if(message.method==="initialize") return response(message.id,{protocolVersion:"2025-03-26",capabilities:{tools:{}},serverInfo:{name:"sol-advisor",version:"0.5.0"}});
  if(message.method==="ping") return response(message.id,{});
  if(message.method==="tools/list") return response(message.id,{tools});
  if(message.method==="tools/call") {
    if(!message.params||typeof message.params.name!=="string"||message.params.arguments===null||typeof (message.params.arguments??{})!=="object"||Array.isArray(message.params.arguments)) return response(message.id,undefined,new Error("invalid tools/call parameters"),-32602);
    try { const value=await callTool(message.params.name,message.params.arguments??{}); return response(message.id,{content:[{type:"text",text:JSON.stringify(value,null,2)}],structuredContent:value}); } catch(e){ const messageText=e instanceof Error?e.message:String(e); return response(message.id,{content:[{type:"text",text:messageText}],isError:true}); }
  }
  return response(message.id,undefined,new Error(`method not found: ${message.method}`),-32601);
}
async function main(){
  let buffer=""; const maxLine=1024*1024;
  for await (const chunk of Bun.stdin.stream()) {
    buffer+=new TextDecoder().decode(chunk,{stream:true});
    if(buffer.length>maxLine&&!buffer.includes("\n")){ process.stdout.write(JSON.stringify(response(null,undefined,new Error("JSON-RPC line exceeds 1 MiB"),-32700))+"\n"); buffer=""; continue; }
    let i; while((i=buffer.indexOf("\n"))>=0){ const raw=buffer.slice(0,i); buffer=buffer.slice(i+1); if(!raw.trim())continue; if(raw.length>maxLine){process.stdout.write(JSON.stringify(response(null,undefined,new Error("JSON-RPC line exceeds 1 MiB"),-32700))+"\n");continue;} let out; try{out=await handle(JSON.parse(raw));}catch(e){out=response(null,undefined,e,-32700)} if(out) process.stdout.write(JSON.stringify(out)+"\n"); }
  }
  if(buffer.trim()){ let out; try{out=await handle(JSON.parse(buffer));}catch(e){out=response(null,undefined,e,-32700)} if(out) process.stdout.write(JSON.stringify(out)+"\n"); }
}
if(import.meta.main) await main();
