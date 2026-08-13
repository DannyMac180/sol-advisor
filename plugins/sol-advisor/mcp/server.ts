#!/usr/bin/env bun
import { createHash, randomUUID } from "node:crypto";
import { existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync, copyFileSync, chmodSync, linkSync, statSync, openSync, fsyncSync, closeSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

export const CONFIG_SCHEMA_VERSION = 2;
export const MANAGED_MARKER = "sol-advisor-managed:v1";
const previewPlans=new Map<string,{digest:string;expires:number;userToken?:string;hardToken?:string;used:boolean}>();
let transactionFaultForTests:((point:string)=>void)|undefined;
export function __setManifestWriteFaultForTests(fault:((point:string)=>void)|undefined){transactionFaultForTests=fault;}
export const CLIENTS = ["codex", "cursor", "vscode", "github-copilot", "kiro"] as const;
export type Client = typeof CLIENTS[number];
export type Scope = "project" | "user";
export type RoleName = "routine" | "high" | "hard" | "advisor";
export type LegacyRoleName = Exclude<RoleName,"hard">;
export type MachineTier = "default" | "fast";
export type RolePreference = { model: string; effort?: string; machineTier: "default"; readonly?: boolean };
export type Preferences = {
  schemaVersion: 2; client: Client; scope: Scope;
  orchestrator: { model: "inherit"; recommendation?: { model: string; effort?: string } };
  roles: { routine: RolePreference; high: RolePreference; hard: RolePreference; advisor: RolePreference };
  hardRoute: { status: "ready" | "pending-consent" | "runtime-pending" };
  fallbackPolicy: "fail-closed"; fallbacks: string[];
  appTaskLane?: { enabled: boolean; model: "gpt-5.6-luna"; effort: "max" };
  profileKey: string; workspace: string; createdAt: string; updatedAt: string; pluginVersion: string;
};
type LegacyRolePreference = { model: string; effort?: string; readonly?: boolean };
type LegacyPreferences = Omit<Preferences,"schemaVersion"|"roles"|"hardRoute"> & {
  schemaVersion: 1;
  roles: { routine: LegacyRolePreference; high: LegacyRolePreference; advisor: LegacyRolePreference };
};
type ManagedFile = { profileKey: string; path: string; hash: string; backup?: string };
type Manifest = { schemaVersion: 1; files: ManagedFile[]; updatedAt: string };

const pluginRoot = resolve(import.meta.dir, "..");
let pinnedDataDir:{lexical:string;real:string;dev:number;ino:number}|undefined;
export function __resetDataPinForTests(){pinnedDataDir=undefined;}
function dataDir(): string {
  const raw=process.env.PLUGIN_DATA;
  if (!raw || !isAbsolute(raw)) throw new Error("PLUGIN_DATA must be an explicit absolute existing directory");
  const lexical=resolve(raw), forbidden=new Set([resolve(sep),realpathSync(homedir()),pluginRoot]);
  if(forbidden.has(lexical)) throw new Error("PLUGIN_DATA cannot be filesystem root, home, or plugin root");
  let cursor=resolve(sep); for(const part of relative(resolve(sep),lexical).split(sep).filter(Boolean)){cursor=join(cursor,part);if(existsSync(cursor)&&lstatSync(cursor).isSymbolicLink())throw new Error(`PLUGIN_DATA has symlink ancestor: ${cursor}`);}
  if (!existsSync(lexical) || !lstatSync(lexical).isDirectory() || lstatSync(lexical).isSymbolicLink()) throw new Error("PLUGIN_DATA must be an existing non-symlink directory");
  const actual=realpathSync(lexical), st=statSync(actual), pinned=pinnedDataDir;
  if((st.mode&0o077)!==0)throw new Error("PLUGIN_DATA must be private (no group/world permission bits)");
  if(pinned&&(pinned.lexical!==lexical||pinned.real!==actual||pinned.dev!==st.dev||pinned.ino!==st.ino))throw new Error("PLUGIN_DATA identity changed during this server process");
  if(!pinned)pinnedDataDir={lexical,real:actual,dev:st.dev,ino:st.ino}; return actual;
}
function configPath() { return join(dataDir(), "config.json"); }
function manifestPath() { return join(dataDir(), "managed-files.json"); }
function backupDir(){const root=dataDir(),path=join(root,"backups");if(!existsSync(path))mkdirSync(path,{mode:0o700});const info=lstatSync(path);if(info.isSymbolicLink()||!info.isDirectory())throw new Error("PLUGIN_DATA backups must be a real directory");const actual=realpathSync(path),rel=relative(root,actual);if(rel!=="backups"||isAbsolute(rel)||rel.startsWith(".."))throw new Error("PLUGIN_DATA backups escapes the pinned data root");if((statSync(actual).mode&0o077)!==0)throw new Error("PLUGIN_DATA backups must be private");return actual;}
function sha(text: string | Uint8Array) { return createHash("sha256").update(text).digest("hex"); }
function syncFile(path:string){const fd=openSync(path,"r");try{fsyncSync(fd);}finally{closeSync(fd);}}
function syncDir(path:string){const fd=openSync(path,"r");try{fsyncSync(fd);}finally{closeSync(fd);}}
function atomicWrite(path: string, text: string) {
  mkdirSync(dirname(path), { recursive: true });
  const temp = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  try { writeFileSync(temp, text, { encoding: "utf8", mode: 0o600, flag: "wx" }); chmodSync(temp,0o600); syncFile(temp); renameSync(temp, path); syncDir(dirname(path)); }
  catch(error){ if(existsSync(temp)) rmSync(temp,{force:true}); throw error; }
}
function readJson(path: string): unknown { return JSON.parse(readFileSync(path, "utf8")); }
function validateLegacyPreferences(value:any): string[] {
  const errors:string[]=[];
  if(!value||typeof value!=="object"||Array.isArray(value)) return ["legacy preferences must be an object"];
  const allowed=["schemaVersion","client","scope","orchestrator","roles","fallbackPolicy","fallbacks","appTaskLane","profileKey","workspace","createdAt","updatedAt","pluginVersion"];
  for(const key of Object.keys(value)) if(!allowed.includes(key)) errors.push(`legacy preferences contains unknown field ${key}`);
  const secretLike=/(secret|token|password|api.?key|credential|private.?key)/i;
  const nested=(object:any,allowedKeys:string[],label:string)=>{if(!object||typeof object!=="object"||Array.isArray(object)){errors.push(`${label} must be an object`);return;}for(const key of Object.keys(object)){if(secretLike.test(key))errors.push(`${label} contains forbidden secret-like field ${key}`);else if(!allowedKeys.includes(key))errors.push(`${label} contains unknown field ${key}`);}};
  nested(value.orchestrator,["model","recommendation"],"legacy orchestrator");
  if(value.orchestrator?.recommendation!==undefined)nested(value.orchestrator.recommendation,["model","effort"],"legacy orchestrator recommendation");
  nested(value.roles,["routine","high","advisor"],"legacy roles");
  if(value.appTaskLane!==undefined)nested(value.appTaskLane,["enabled","model","effort"],"legacy appTaskLane");
  if(value.schemaVersion!==1) errors.push("legacy schemaVersion must be 1");
  if(!CLIENTS.includes(value.client)) errors.push("client is unsupported");
  if(value.scope!=="project"&&value.scope!=="user") errors.push("scope must be project or user");
  if(value.orchestrator?.model!=="inherit") errors.push("orchestrator must inherit the parent model and effort");
  if(value.fallbackPolicy!=="fail-closed"||!Array.isArray(value.fallbacks)||value.fallbacks.length) errors.push("fallbacks must be empty with fail-closed policy");
  for(const role of ["routine","high","advisor"] as LegacyRoleName[]){const pref=value.roles?.[role];if(!pref||typeof pref!=="object"){errors.push(`roles.${role} is required`);continue;}for(const key of Object.keys(pref))if(secretLike.test(key))errors.push(`legacy role ${role} contains forbidden secret-like field ${key}`);else if(!["model","effort","readonly"].includes(key))errors.push(`legacy role ${role} contains unknown field ${key}`);exactString(pref.model,`roles.${role}.model`,errors);if(pref.effort!==undefined)exactString(pref.effort,`roles.${role}.effort`,errors);}
  if(value.roles?.advisor?.readonly!==true) errors.push("advisor readonly preference must be true");
  return errors;
}
function migrateV1Profile(legacy:LegacyPreferences): Preferences {
  const convert=(role:LegacyRoleName,readonly=false):RolePreference=>({model:legacy.roles[role].model,...(legacy.roles[role].effort===undefined?{}:{effort:legacy.roles[role].effort}),machineTier:"default",...(readonly?{readonly:true}: {})});
  return {...legacy,schemaVersion:2,roles:{routine:convert("routine"),high:convert("high"),hard:{model:legacy.roles.advisor.model,...(legacy.roles.advisor.effort===undefined?{}:{effort:legacy.roles.advisor.effort}),machineTier:"default"},advisor:convert("advisor",true)},hardRoute:{status:"pending-consent"},pluginVersion:"0.6.0"};
}
function migrateV1Config(raw:any): any {
  if(!raw||raw.schemaVersion!==1||!raw.profiles||typeof raw.profiles!=="object"||typeof raw.activeProfile!=="string") throw new Error("legacy configuration is malformed");
  const allowed=["schemaVersion","activeProfile","profiles"];
  if(Object.keys(raw).some(key=>!allowed.includes(key)||/(secret|token|password|api.?key|credential|private.?key)/i.test(key))) throw new Error("legacy configuration contains unknown or secret-like top-level fields");
  const profiles:Record<string,Preferences>={};
  for(const [key,value] of Object.entries(raw.profiles)){const errors=validateLegacyPreferences(value);if(errors.length)throw new Error(`legacy profile ${key} is corrupt: ${errors.join("; ")}`);profiles[key]=migrateV1Profile(value as LegacyPreferences);}
  if(!profiles[raw.activeProfile]) throw new Error("legacy active profile is missing");
  const migrated={schemaVersion:2,activeProfile:raw.activeProfile,profiles};
  atomicWrite(configPath(),JSON.stringify(migrated,null,2)+"\n");
  return migrated;
}
function configState(): { status: "missing"|"ready"|"schema-old"|"corrupt"; preferences?: Preferences; detail?: string } {
  if (!existsSync(configPath())) return { status: "missing" };
  try {
    let raw: any = readJson(configPath());
    if(raw?.schemaVersion===1) raw=migrateV1Config(raw);
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
  unknown(value,["schemaVersion","client","scope","orchestrator","roles","hardRoute","fallbackPolicy","fallbacks","appTaskLane","profileKey","workspace","createdAt","updatedAt","pluginVersion"],"preferences");
  unknown(value.orchestrator,["model","recommendation"],"orchestrator"); unknown(value.orchestrator?.recommendation,["model","effort"],"orchestrator recommendation");
  unknown(value.roles,["routine","high","hard","advisor"],"roles"); for(const role of ["routine","high","hard","advisor"]) unknown(value.roles?.[role],["model","effort","machineTier","readonly"],`role ${role}`);
  unknown(value.hardRoute,["status"],"hardRoute");
  unknown(value.appTaskLane,["enabled","model","effort"],"appTaskLane");
  if (value.schemaVersion !== 2) errors.push("schemaVersion must be 2");
  if (!CLIENTS.includes(value.client)) errors.push("client is unsupported");
  if (!(value.scope === "project" || value.scope === "user")) errors.push("scope must be project or user");
  if (value.orchestrator?.model !== "inherit") errors.push("orchestrator must inherit the parent model and effort");
  if (value.fallbackPolicy !== "fail-closed" || !Array.isArray(value.fallbacks) || value.fallbacks.length !== 0) errors.push("fallbacks must be empty with fail-closed policy");
  for (const role of ["routine", "high", "hard", "advisor"] as RoleName[]) {
    const r = value.roles?.[role];
    if (!r || typeof r !== "object") { errors.push(`roles.${role} is required`); continue; }
    exactString(r.model, `roles.${role}.model`, errors);
    if (r.effort !== undefined) exactString(r.effort, `roles.${role}.effort`, errors);
    if(r.machineTier!=="default") errors.push(`roles.${role}.machineTier must be default`);
  }
  if (value.roles?.advisor?.readonly !== true) errors.push("advisor readonly preference must be true");
  if(!["ready","pending-consent","runtime-pending"].includes(value.hardRoute?.status)) errors.push("hardRoute status is invalid");
  if(typeof value.profileKey!=="string"||!value.profileKey||typeof value.workspace!=="string"||!isAbsolute(value.workspace)) errors.push("profileKey and absolute workspace are required");
  if (["vscode", "github-copilot", "kiro"].includes(value.client)) {
    for (const role of ["routine", "high", "hard", "advisor"] as RoleName[]) if (value.roles?.[role]?.effort !== undefined) errors.push(`${value.client} cannot persist a per-agent effort claim for ${role}`);
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
  if (role === "high") return "Implement medium-routine work that needs more care than routine work, while preserving the settled architecture, interfaces, and concurrent edits.";
  return "Implement hard, security-sensitive, migration, concurrency, algorithmic, debugging, or wide-blast-radius work within the settled architecture. Surface ambiguity, preserve concurrent edits, and report verification evidence.";
}
function filenames(client: Client): Record<RoleName,string> {
  const ext = client === "codex" ? ".toml" : client === "vscode" || client === "github-copilot" ? ".agent.md" : ".md";
  return { routine:`sol-advisor-routine${ext}`, high:`sol-advisor-high${ext}`, hard:`sol-advisor-hard${ext}`, advisor:`sol-advisor-advisor${ext}` };
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
  const files = (["routine","high","hard","advisor"] as RoleName[]).map(role => {
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
  const hardConsentToken=preferences.hardRoute.status==="pending-consent"?`CONFIRM HARD ${nonce}`:undefined;
  if(hardConsentToken) previewPlans.get(confirmationToken)!.hardToken=hardConsentToken;
  return { client:preferences.client,scope:preferences.scope,workspace,files,warnings,planDigest,targetState,expiresAt:new Date(Date.now()+10*60_000).toISOString(),confirmationToken,userScopeConfirmationToken,hardConsentToken,afterInstall:"Start a new chat or reload the client so native role discovery sees the adapter files." };
}
function loadManifest(): Manifest { if(!existsSync(manifestPath())) return {schemaVersion:1,files:[],updatedAt:new Date().toISOString()}; let x:any; try{x=readJson(manifestPath());}catch(error){throw new Error(`managed-file manifest is corrupt: ${String(error)}`);} if(x?.schemaVersion!==1||!Array.isArray(x.files)) throw new Error("managed-file manifest schema is unsupported"); const paths=new Set<string>(); for(const file of x.files){if(!file||typeof file.profileKey!=="string"||typeof file.path!=="string"||!isAbsolute(file.path)||typeof file.hash!=="string"||!/^[a-f0-9]{64}$/.test(file.hash))throw new Error("managed-file manifest entry is invalid");if(paths.has(file.path))throw new Error(`managed-file manifest contains duplicate path ownership: ${file.path}`);paths.add(file.path);} return x; }
function requireExactManaged(path:string, hashValue:string) { const text=readFileSync(path,"utf8"); if(!text.includes(MANAGED_MARKER)||sha(text)!==hashValue) throw new Error(`managed file changed; refusing: ${path}`); }
type TxEntry={target:string;stage?:string;backup?:string;quarantine?:string;newHash:string;originalHash?:string;wasMissing?:boolean};
type TransactionJournal={schemaVersion:1;operation:"install"|"uninstall";phase:"prepared"|"targets-committed"|"manifest-committed";committed:number;entries:TxEntry[];manifestExisted:boolean;originalManifest:string;newManifest:string;profileKey:string};
function journalPath(){return join(dataDir(),"transaction.json");}
function writeJournal(tx:TransactionJournal){atomicWrite(journalPath(),JSON.stringify(tx,null,2)+"\n");}
function removeJournal(){if(existsSync(journalPath())){rmSync(journalPath(),{force:true});syncDir(dirname(journalPath()));}}
function currentHash(path:string){return existsSync(path)&&lstatSync(path).isFile()&&!lstatSync(path).isSymbolicLink()?sha(readFileSync(path)):undefined;}
function removeExact(path:string,expected:string,label:string){if(currentHash(path)!==expected)throw new Error(`${label} hash mismatch: ${path}`);rmSync(path,{force:true});syncDir(dirname(path));}
function restoreManifest(tx:TransactionJournal){
  const actual=currentHash(manifestPath()),originalHash=sha(tx.originalManifest),newHash=sha(tx.newManifest);
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
  const rendered=renderAdapter(state.preferences!,state.preferences!.workspace).files;
  const expected=new Set(rendered.map(f=>f.path)),legacy=new Set(rendered.filter(f=>f.role!=="hard").map(f=>f.path)),backupRoot=join(dataDir(),"backups"),entryKeys=["target","stage","backup","quarantine","newHash","originalHash","wasMissing"];
  const journalTargets=new Set(tx.entries.map((e:any)=>e?.target)),isCurrent=tx.entries.length===expected.size&&journalTargets.size===expected.size&&[...expected].every(path=>journalTargets.has(path)),isLegacy=tx.entries.length===legacy.size&&journalTargets.size===legacy.size&&[...legacy].every(path=>journalTargets.has(path));if(!isCurrent&&!isLegacy)throw new Error("transaction journal target set is incomplete or duplicated");
  const validSibling=(candidate:any,target:string,suffix:string)=>{if(typeof candidate!=="string"||dirname(candidate)!==dirname(target))return false;const name=basename(candidate),prefix=`.${basename(target)}.`,tail=`.${suffix}`;return name.startsWith(prefix)&&name.endsWith(tail)&&/^[0-9a-f-]{36}$/.test(name.slice(prefix.length,-tail.length));};
  for(const e of tx.entries){
    if(!e||keys(e).some(k=>!entryKeys.includes(k))||typeof e.target!=="string"||!expected.has(e.target)||typeof e.newHash!=="string"||(tx.operation==="install"&&!/^[a-f0-9]{64}$/.test(e.newHash))||(e.originalHash!==undefined&&!/^[a-f0-9]{64}$/.test(e.originalHash))||(e.wasMissing!==undefined&&typeof e.wasMissing!=="boolean"))throw new Error("transaction journal entry is invalid");
    if(e.stage!==undefined&&!validSibling(e.stage,e.target,"stage"))throw new Error("transaction stage path is invalid");
    if(e.quarantine!==undefined&&!validSibling(e.quarantine,e.target,"quarantine"))throw new Error("transaction quarantine path is invalid");
    if(e.backup!==undefined&&(typeof e.backup!=="string"||dirname(e.backup)!==backupRoot))throw new Error("transaction backup path is invalid");
  }
}
function recoverTransaction(){
  if(!existsSync(journalPath()))return;let tx:TransactionJournal;try{tx=readJson(journalPath()) as TransactionJournal;}catch{throw new Error("transaction journal is corrupt; manual recovery required");}
  validateJournal(tx);
  if(tx.phase==="manifest-committed"){for(const e of tx.entries){if(e.stage&&existsSync(e.stage))removeExact(e.stage,e.newHash,"recovery stage");if(e.quarantine&&existsSync(e.quarantine))removeExact(e.quarantine,e.originalHash!,"recovery quarantine");}removeJournal();return;}
  if(tx.operation==="install")rollbackInstall(tx);else if(tx.operation==="uninstall")rollbackUninstall(tx);else throw new Error("unknown transaction operation");
}
function installAdapter(args:any) {
  const state=configState(); if(state.status!=="ready") throw new Error(`setup is ${state.status}; run the parent-chat setup interview first`);
  rejectUnknown(args,["workspace","confirmationToken","userScopeConfirmationToken","hardConsentToken"],"install");
  for(const key of ["workspace","confirmationToken","userScopeConfirmationToken","hardConsentToken"]) if(typeof args[key]==="string"&&/[\r\n\0]/.test(args[key])) throw new Error(`${key} contains control characters`);
  const preview=renderAdapter(state.preferences!,args.workspace), plan=previewPlans.get(args.confirmationToken);
  if(!plan||plan.used||plan.expires<Date.now()||plan.digest!==preview.planDigest) throw new Error("installation requires the exact unexpired one-time preview confirmation token and unchanged target state");
  if(preview.scope==="user"&&args.userScopeConfirmationToken!==plan.userToken) throw new Error("user-scope installation requires the separate exact user-scope token");
  if(plan.hardToken&&args.hardConsentToken!==plan.hardToken) throw new Error("four-role installation requires the separate exact hard consent token");
  plan.used=true;
  const manifest=loadManifest(), previous=new Map(manifest.files.map(f=>[f.path,f]));
  for(const f of preview.files){const known=previous.get(f.path);if(known&&known.profileKey!==state.preferences!.profileKey)throw new Error(`adapter path is owned by a different profile; explicit uninstall required: ${f.path}`);if(existsSync(f.path)){if(!known)throw new Error(`unmanaged/conflicting file refused: ${f.path}`);requireExactManaged(f.path,known.hash);}}
  const originalManifest=existsSync(manifestPath())?readFileSync(manifestPath(),"utf8"):"", targetState=new Map(preview.targetState.map((x:any)=>[x.path,x.state]));
  const entries:TxEntry[]=[],installed:ManagedFile[]=[];
  for(const f of preview.files){const expected=targetState.get(f.path),wasMissing=expected==="missing",backup=wasMissing?undefined:join(dataDir(),"backups",`${Date.now()}-${randomUUID()}-${basename(f.path)}-${String(expected).slice(0,12)}.bak`),stage=join(dirname(f.path),`.${basename(f.path)}.${randomUUID()}.stage`),quarantine=wasMissing?undefined:join(dirname(f.path),`.${basename(f.path)}.${randomUUID()}.quarantine`);entries.push({target:f.path,stage,backup,quarantine,newHash:f.hash,originalHash:wasMissing?undefined:String(expected),wasMissing});installed.push({profileKey:state.preferences!.profileKey,path:f.path,hash:f.hash,backup});}
  const retained=manifest.files.filter(f=>f.profileKey!==state.preferences!.profileKey),newManifest=JSON.stringify({schemaVersion:1,files:[...retained,...installed],updatedAt:new Date().toISOString()},null,2)+"\n";
  const tx:TransactionJournal={schemaVersion:1,operation:"install",phase:"prepared",committed:0,entries,manifestExisted:existsSync(manifestPath()),originalManifest,newManifest,profileKey:state.preferences!.profileKey};writeJournal(tx);
  try{
    for(const e of entries){mkdirSync(dirname(e.target),{recursive:true});if(e.backup){const privateBackups=backupDir();if(dirname(e.backup)!==privateBackups)throw new Error("backup destination escaped private backup directory");copyFileSync(e.target,e.backup);chmodSync(e.backup,0o600);syncFile(e.backup);syncDir(dirname(e.backup));if(currentHash(e.backup)!==e.originalHash)throw new Error(`backup hash mismatch: ${e.target}`);}writeFileSync(e.stage!,preview.files.find((f:any)=>f.path===e.target)!.content,{encoding:"utf8",mode:0o600,flag:"wx"});chmodSync(e.stage!,0o600);syncFile(e.stage!);syncDir(dirname(e.stage!));}
    transactionFaultForTests?.("install-before-targets");
    for(let i=0;i<entries.length;i++){const e=entries[i]!;assertNoSymlinkPath(e.target,state.preferences!.scope==="project"?state.preferences!.workspace:realpathSync(homedir()));const actual=currentHash(e.target);if(e.wasMissing){if(actual!==undefined||existsSync(e.target))throw new Error(`target appeared after preview: ${e.target}`);}else{if(actual!==e.originalHash)throw new Error(`managed target changed after preview: ${e.target}`);const before=lstatSync(e.target);transactionFaultForTests?.(`install-before-quarantine-${i+1}`);if(existsSync(e.quarantine!))throw new Error(`install quarantine conflict: ${e.quarantine}`);renameSync(e.target,e.quarantine!);syncDir(dirname(e.target));const quarantined=lstatSync(e.quarantine!);if(quarantined.isSymbolicLink()||!quarantined.isFile()||quarantined.dev!==before.dev||quarantined.ino!==before.ino||currentHash(e.quarantine!)!==e.originalHash){if(!existsSync(e.target)){renameSync(e.quarantine!,e.target);syncDir(dirname(e.target));}throw new Error(`install quarantine identity/hash mismatch: ${e.target}`);}}linkSync(e.stage!,e.target);rmSync(e.stage!,{force:true});syncDir(dirname(e.target));if(currentHash(e.target)!==e.newHash)throw new Error(`committed target hash mismatch: ${e.target}`);tx.committed=i+1;tx.phase="targets-committed";writeJournal(tx);transactionFaultForTests?.(`install-target-${i+1}`);}
    atomicWrite(manifestPath(),newManifest);transactionFaultForTests?.("install-manifest-commit");tx.phase="manifest-committed";writeJournal(tx);transactionFaultForTests?.("install-journal-commit");for(const e of entries)if(e.quarantine&&existsSync(e.quarantine))removeExact(e.quarantine,e.originalHash!,"committed quarantine");removeJournal();
  }catch(error){if((error instanceof Error&&error.message==="__SIMULATED_CRASH__")||tx.phase==="manifest-committed")throw error;try{rollbackInstall(tx);}catch(rollback){throw new Error(`${String(error)}; rollback incomplete: ${String(rollback)}`);}throw error;}
  if(state.preferences!.hardRoute.status==="pending-consent"){
    const stored:any=readJson(configPath());
    stored.profiles[state.preferences!.profileKey].hardRoute={status:"runtime-pending"};
    stored.profiles[state.preferences!.profileKey].updatedAt=new Date().toISOString();
    atomicWrite(configPath(),JSON.stringify(stored,null,2)+"\n");
  }
  return {installed:installed.map(x=>x.path),backups:installed.flatMap(x=>x.backup?[x.backup]:[]),guidance:preview.afterInstall};
}
function uninstallAdapter(args:any) {
  const state=configState(); if(state.status!=="ready") throw new Error(`setup is ${state.status}`);const manifest=loadManifest(),selected=manifest.files.filter(f=>f.profileKey===state.preferences!.profileKey);if(!selected.length)return {removed:[]};
  const current=renderAdapter(state.preferences!,state.preferences!.workspace).files;
  const legacy=new Set(current.filter(f=>f.role!=="hard").map(f=>f.path));
  const expected=new Set(current.map(f=>f.path));
  if(selected.some(f=>!expected.has(f.path))||![3,4].includes(selected.length)|| (selected.length===3&&!selected.every(f=>legacy.has(f.path))))throw new Error("managed-file manifest destinations do not match the active client allowlist");
  const token=`UNINSTALL ${sha(JSON.stringify(selected.map(f=>({path:f.path,hash:f.hash}))))}`;if(args.confirmationToken!==token)return {requiresConfirmation:true,confirmationToken:token,files:selected.map(f=>f.path)};
  for(const f of selected)requireExactManaged(f.path,f.hash);
  const originalManifest=readFileSync(manifestPath(),"utf8"),newManifest=JSON.stringify({schemaVersion:1,files:manifest.files.filter(f=>f.profileKey!==state.preferences!.profileKey),updatedAt:new Date().toISOString()},null,2)+"\n";
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
  for(const name of ["routine","high","hard","advisor"] as RoleName[]) rejectUnknown(args.roles?.[name],["model","effort","readonly"],`role ${name}`);
  const now=new Date().toISOString(), existing=configState(), workspace=safeWorkspace(args.workspace);
  const profileKey=`${args.client}:${args.scope}:${workspace}`;
  const role=(name:RoleName,readonly=false)=>({model:args.roles?.[name]?.model,...(args.roles?.[name]?.effort!==undefined?{effort:args.roles[name].effort}:{}),machineTier:"default" as const,...(readonly?{readonly:true}:args.roles?.[name]?.readonly!==undefined?{readonly:args.roles[name].readonly}: {})});
  const candidate:any={schemaVersion:2,client:args.client,scope:args.scope,orchestrator:{model:"inherit",...(args.orchestrator?.recommendation?{recommendation:{model:args.orchestrator.recommendation.model,...(args.orchestrator.recommendation.effort!==undefined?{effort:args.orchestrator.recommendation.effort}:{})}}:{})},roles:{routine:role("routine"),high:role("high"),hard:role("hard"),advisor:role("advisor",true)},hardRoute:{status:"ready"},fallbackPolicy:"fail-closed",fallbacks:[],...(args.appTaskLane?.enabled===true?{appTaskLane:{enabled:true,model:"gpt-5.6-luna",effort:"max"}}:{}),profileKey,workspace,createdAt:existing.preferences?.profileKey===profileKey?existing.preferences.createdAt:now,updatedAt:now,pluginVersion:"0.6.0"};
  const errors=validatePreferences(candidate); if(errors.length) throw new Error(errors.join("; "));
  if(existsSync(configPath())) { const privateBackups=backupDir(),backup=join(privateBackups,`${Date.now()}-config.json.bak`);if(dirname(backup)!==backupDir())throw new Error("config backup destination changed");copyFileSync(configPath(),backup);chmodSync(backup,0o600);syncFile(backup);syncDir(privateBackups); }
  let profiles:Record<string,Preferences>={}; try { const old:any=readJson(configPath()); if(old?.schemaVersion===2&&old.profiles&&typeof old.profiles==="object") profiles=old.profiles; } catch {}
  profiles[profileKey]=candidate; atomicWrite(configPath(),JSON.stringify({schemaVersion:2,activeProfile:profileKey,profiles},null,2)+"\n"); return {saved:true,profileKey,preferences:candidate};
}
type TaskClass="routine"|"medium"|"hard"|"planning"|"review";
type RuntimeEvidence={challenge:string;threadId:string;latestEventAt:string;evidenceSource:"codex-rollout-inspector";executionContext:"parent";agentIdentifier:null;model:string;effort:string;observedRuntimeTier:"default"|"priority"|null;sandboxPolicyType:string;rawTokens:number;modelRounds:number;medianInputTokensPerRound:number|null;medianInputTokensFirst20:number|null;toolCalls:number;compactions:number};
type TargetRuntimeEvidence=Omit<RuntimeEvidence,"executionContext"|"agentIdentifier">&{executionContext:"agent";agentIdentifier:string};
type RouteChallenge={taskClass:TaskClass;profileKey:string;machineTier:MachineTier;issuedAt:number;expires:number;used:boolean};
const routeChallenges=new Map<string,RouteChallenge>();
let routeChallengeNowForTests:(()=>number)|undefined;
export function __setRouteChallengeNowForTests(clock:(()=>number)|undefined){routeChallengeNowForTests=clock;}
function routeNow(){return routeChallengeNowForTests?routeChallengeNowForTests():Date.now();}
const routeChallengeLifetimeMs=5*60_000, routeEvidenceFutureClockSkewMs=5_000;
const uuidPattern=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function routeResult(taskClass:TaskClass,storageRole:RoleName,identifier:string,pref:RolePreference,machineTier:MachineTier,placement:"parent"|"fresh_agent",evidenceStatus:"blocked"|"spawn-required"|"verified",reason:string|null,current?:RuntimeEvidence,target?:TargetRuntimeEvidence,challenge?:string,challengeExpiresAt?:string){const selected=placement==="fresh_agent"&&target?target:current;return {taskClass,storageRole,agentIdentifier:identifier,configured:{model:pref.model,effort:pref.effort,readonly:pref.readonly===true},requestedMachineTier:machineTier,requestedRuntimeTier:machineTier==="fast"?"priority":"default",savedMachineTier:pref.machineTier,observedRuntimeTier:selected?.observedRuntimeTier??null,presentationLabel:machineTier==="fast"?"Fast":"Standard",currentRuntimeEvidence:current??null,targetRuntimeEvidence:target??null,evidenceStatus,blockedReason:reason,executionPlacement:placement,escalated:placement==="fresh_agent",forkContext:false,parallelism:1,...(challenge?{challenge,challengeExpiresAt}: {})};}
function markHardRouteReady(preferences:Preferences){const stored:any=readJson(configPath()),profile=stored?.profiles?.[preferences.profileKey];if(!profile||profile.hardRoute?.status!=="runtime-pending")throw new Error("hard route state changed before target proof could be recorded");const privateBackups=backupDir(),backup=join(privateBackups,`${Date.now()}-config.json.bak`);if(dirname(backup)!==privateBackups)throw new Error("config backup destination changed");copyFileSync(configPath(),backup);chmodSync(backup,0o600);syncFile(backup);syncDir(privateBackups);profile.hardRoute={status:"ready"};profile.updatedAt=new Date().toISOString();atomicWrite(configPath(),JSON.stringify(stored,null,2)+"\n");}
function resolveRoute(args:any){
  const state=configState();if(state.status!=="ready")throw new Error(`setup is ${state.status}`);const prefs=state.preferences!;
  const aggregateEvidenceFields=new Set(["rawTokens","medianInputTokensPerRound","medianInputTokensFirst20"]);
  const assertRuntimeEvidenceSafe=(value:any,path:string)=>{if(!value||typeof value!=="object"||Array.isArray(value)){assertSafeInput(value,path);return;}for(const [key,item] of Object.entries(value)){if(!aggregateEvidenceFields.has(key)&&/(secret|token|password|api.?key|credential|private.?key)/i.test(key))throw new Error(`forbidden secret-like field: ${path}.${key}`);assertSafeInput(item,`${path}.${key}`);}};
  assertRuntimeEvidenceSafe(args.currentRuntimeEvidence,"currentRuntimeEvidence");assertRuntimeEvidenceSafe(args.targetRuntimeEvidence,"targetRuntimeEvidence");assertSafeInput(args.fastOverride,"fastOverride");
  const exactObject=(value:any,allowed:string[],label:string)=>{if(!value||typeof value!=="object"||Array.isArray(value))throw new Error(`${label} is required`);rejectUnknown(value,allowed,label);};
  if(args.fastOverride!==undefined)exactObject(args.fastOverride,["bounded","oneRoute"],"fastOverride");
  const taskClass=args.taskClass as TaskClass, route:{storageRole:RoleName}={routine:{storageRole:"routine"},medium:{storageRole:"high"},hard:{storageRole:"hard"},planning:{storageRole:"advisor"},review:{storageRole:"advisor"}}[taskClass];
  if(!route)throw new Error("taskClass is unsupported");const machineTier:MachineTier=args.machineTier??"default";if(machineTier!=="default"&&machineTier!=="fast")throw new Error("machineTier must be default or fast");
  const pref=prefs.roles[route.storageRole],identifier=prefs.client==="codex"?`sol_advisor_${route.storageRole}`:`sol-advisor-${route.storageRole}`;
  const initialBlocked=(reason:string,placement:"parent"|"fresh_agent"="parent")=>routeResult(taskClass,route.storageRole,identifier,pref,machineTier,placement,"blocked",reason);
  if(machineTier==="fast"&&(!args.fastOverride||args.fastOverride.bounded!==true||args.fastOverride.oneRoute!==true))return initialBlocked("Fast requires an explicit bounded one-route override");
  if(machineTier==="fast"&&(taskClass!=="routine"||pref.model!=="gpt-5.6-luna"||pref.effort!=="max"))return initialBlocked("Fast is available only for the exact routine Luna/max route");
  if(route.storageRole==="hard"&&prefs.hardRoute.status!=="runtime-pending"&&prefs.hardRoute.status!=="ready")return initialBlocked("hard route is pending four-role preview consent");
  if(!pref.effort)return initialBlocked("configured effort is unavailable");
  if(args.currentRuntimeEvidence===undefined&&args.targetRuntimeEvidence===undefined&&args.challenge===undefined){const issuedAt=routeNow();for(const [key,old] of routeChallenges)if(old.used||old.expires<=issuedAt)routeChallenges.delete(key);const challenge=randomUUID(),expires=issuedAt+routeChallengeLifetimeMs;routeChallenges.set(challenge,{taskClass,profileKey:prefs.profileKey,machineTier,issuedAt,expires,used:false});return {taskClass,requestedMachineTier:machineTier,requestedRuntimeTier:machineTier==="fast"?"priority":"default",presentationLabel:machineTier==="fast"?"Fast":"Standard",evidenceStatus:"challenge-required",blockedReason:null,challenge,challengeIssuedAt:new Date(issuedAt).toISOString(),challengeExpiresAt:new Date(expires).toISOString(),forkContext:false,parallelism:1};}
  if(args.currentRuntimeEvidence===undefined)throw new Error("currentRuntimeEvidence is required after a route challenge is issued");
  if(typeof args.challenge!=="string"||!uuidPattern.test(args.challenge))throw new Error("challenge must be an unmodified lowercase UUID issued by resolve_route");
  const challenge=routeChallenges.get(args.challenge),now=routeNow();if(!challenge)throw new Error("route challenge is unknown");if(challenge.used)throw new Error("route challenge was already consumed");if(challenge.expires<=now)throw new Error("route challenge expired");if(challenge.taskClass!==taskClass||challenge.profileKey!==prefs.profileKey||challenge.machineTier!==machineTier)throw new Error("route challenge does not match this task, profile, or machine tier");
  const evidenceFields=["challenge","threadId","latestEventAt","evidenceSource","executionContext","agentIdentifier","model","effort","observedRuntimeTier","sandboxPolicyType","rawTokens","modelRounds","medianInputTokensPerRound","medianInputTokensFirst20","toolCalls","compactions"];
  exactObject(args.currentRuntimeEvidence,evidenceFields,"currentRuntimeEvidence");if(args.targetRuntimeEvidence!==undefined)exactObject(args.targetRuntimeEvidence,evidenceFields,"targetRuntimeEvidence");
  const current=args.currentRuntimeEvidence as RuntimeEvidence,target=args.targetRuntimeEvidence as TargetRuntimeEvidence|undefined;
  const blocked=(reason:string,placement:"parent"|"fresh_agent"="parent")=>routeResult(taskClass,route.storageRole,identifier,pref,machineTier,placement,"blocked",reason,current,target);
  const invalidated=(reason:string,placement:"parent"|"fresh_agent"="parent")=>{challenge.used=true;return blocked(reason,placement);};
  const validateEvidence=(e:RuntimeEvidence|TargetRuntimeEvidence,label:string,targetEvidence=false)=>{if(e.challenge!==args.challenge)throw new Error(`${label}.challenge does not match the active route challenge`);if(typeof e.threadId!=="string"||!uuidPattern.test(e.threadId))throw new Error(`${label}.threadId must be a lowercase UUID`);if(typeof e.latestEventAt!=="string"||Number.isNaN(Date.parse(e.latestEventAt)))throw new Error(`${label}.latestEventAt must be a parseable timestamp`);const eventAt=Date.parse(e.latestEventAt);if(eventAt<challenge.issuedAt||eventAt>now+routeEvidenceFutureClockSkewMs)throw new Error(`${label}.latestEventAt is outside the bounded fresh-evidence window`);const exactAgentIdentifier=typeof e.agentIdentifier==="string"&&e.agentIdentifier.trim()!==""&&e.agentIdentifier===e.agentIdentifier.trim()&&!/[\r\n\0]/.test(e.agentIdentifier);if(e.evidenceSource!=="codex-rollout-inspector"||e.executionContext!==(targetEvidence?"agent":"parent")||(targetEvidence?!exactAgentIdentifier:e.agentIdentifier!==null))return false;for(const field of ["model","effort","sandboxPolicyType"] as const)if(typeof e[field]!=="string"||!e[field].trim()||e[field]!==e[field].trim()||/[\r\n\0]/.test(e[field]))throw new Error(`${label}.${field} must be an exact non-empty identifier`);if(!["default","priority",null].includes(e.observedRuntimeTier))throw new Error(`${label}.observedRuntimeTier is invalid`);for(const field of ["rawTokens","modelRounds","toolCalls","compactions"] as const)if(!Number.isSafeInteger(e[field])||e[field]<0)throw new Error(`${label}.${field} must be a non-negative safe integer`);for(const field of ["medianInputTokensPerRound","medianInputTokensFirst20"] as const)if(e[field]!==null&&(!Number.isFinite(e[field])||e[field]<0))throw new Error(`${label}.${field} must be null or a non-negative number`);return true;};
  if(!validateEvidence(current,"currentRuntimeEvidence"))return invalidated("current runtime evidence provenance must be the parent inspector record");
  if(target&&!validateEvidence(target,"targetRuntimeEvidence",true))return invalidated("target runtime evidence provenance must be the agent inspector record","fresh_agent");
  if(target&&target.threadId===current.threadId)return invalidated("current and target runtime evidence must use different thread IDs","fresh_agent");
  const expectedTier=machineTier==="fast"?"priority":"default";
  const exact=(e:RuntimeEvidence|TargetRuntimeEvidence,targetEvidence=false)=>e.evidenceSource==="codex-rollout-inspector"&&e.executionContext===(targetEvidence?"agent":"parent")&&e.agentIdentifier===(targetEvidence?identifier:null)&&e.model===pref.model&&e.effort===pref.effort&&(machineTier!=="fast"||e.observedRuntimeTier==="priority")&&(machineTier==="fast"||e.observedRuntimeTier===null||e.observedRuntimeTier===expectedTier)&&(pref.readonly?e.sandboxPolicyType==="read-only":e.sandboxPolicyType!=="read-only");
  const requiresFresh=taskClass==="review"||route.storageRole==="hard"&&prefs.hardRoute.status==="runtime-pending"||!exact(current);
  if(!requiresFresh){challenge.used=true;const budget=machineTier==="fast"?{toolCalls:10,rawTokens:1_000_000,compactions:0,restartOnExpansion:"routine Luna/default"}:taskClass==="planning"?{toolCalls:25,rawTokens:2_500_000,compactions:0}:{toolCalls:50,rawTokens:5_000_000,compactions:1};return {...routeResult(taskClass,route.storageRole,identifier,pref,machineTier,"parent","verified",null,current,target),budget,outputLimit:{bytes:8192,lines:200},handoffTokenLimit:2000,contextPolicy:"batch independent reads; never carry raw logs or unchanged context"};}
  if(!target)return routeResult(taskClass,route.storageRole,identifier,pref,machineTier,"fresh_agent","spawn-required","spawn fresh exact target and supply targetRuntimeEvidence",current,undefined,args.challenge,new Date(challenge.expires).toISOString());
  if(!exact(target,true))return invalidated("target runtime evidence does not match the configured route","fresh_agent");
  challenge.used=true;
  if(route.storageRole==="hard"&&prefs.hardRoute.status==="runtime-pending")markHardRouteReady(prefs);
  const fast=machineTier==="fast",budget=fast?{toolCalls:10,rawTokens:1_000_000,compactions:0,restartOnExpansion:"routine Luna/default"}:taskClass==="planning"||taskClass==="review"?{toolCalls:25,rawTokens:2_500_000,compactions:0}:{toolCalls:50,rawTokens:5_000_000,compactions:1};
  return {...routeResult(taskClass,route.storageRole,identifier,pref,machineTier,"fresh_agent","verified",null,current,target),budget,outputLimit:{bytes:8192,lines:200},handoffTokenLimit:2000,contextPolicy:"batch independent reads; never carry raw logs or unchanged context"};
}
function resetConfiguration(args:any) { const live=loadManifest().files; if(live.length) throw new Error("reset refused while managed adapter files are installed; uninstall them first"); const token="RESET SOL ADVISOR CONFIGURATION"; if(args.confirmationToken!==token) return {requiresConfirmation:true,confirmationToken:token}; for(const path of [configPath(),manifestPath(),join(dataDir(),"backups")]) if(existsSync(path)) rmSync(path,{recursive:true,force:true}); previewPlans.clear(); return {reset:true,purged:true}; }
const objectSchema=(properties:Record<string,unknown>={},required:string[]=[])=>({type:"object",properties,required,additionalProperties:false});
const str={type:"string"};
const nonnegativeInteger={type:"integer",minimum:0}, nonnegativeNumber={type:"number",minimum:0};
const roleSchema={type:"object",properties:{model:str,effort:str,readonly:{type:"boolean"}},required:["model"],additionalProperties:false};
const runtimeEvidenceProperties={challenge:str,threadId:str,latestEventAt:str,evidenceSource:{const:"codex-rollout-inspector"},executionContext:{type:"string",enum:["parent","agent"]},agentIdentifier:{type:["string","null"]},model:str,effort:str,observedRuntimeTier:{type:["string","null"],enum:["default","priority",null]},sandboxPolicyType:str,rawTokens:nonnegativeInteger,modelRounds:nonnegativeInteger,medianInputTokensPerRound:{anyOf:[nonnegativeNumber,{type:"null"}]},medianInputTokensFirst20:{anyOf:[nonnegativeNumber,{type:"null"}]},toolCalls:nonnegativeInteger,compactions:nonnegativeInteger};
const runtimeEvidenceSchema={type:"object",properties:runtimeEvidenceProperties,required:Object.keys(runtimeEvidenceProperties),additionalProperties:false};
export const tools = [
  {name:"get_setup_status",description:"Report missing, ready, schema-old, or corrupt setup state",inputSchema:objectSchema()},
  {name:"get_preferences",description:"Read non-secret logical preferences",inputSchema:objectSchema()},
  {name:"save_preferences",description:"Validate and atomically save schema-v2 role preferences",inputSchema:objectSchema({client:{type:"string",enum:CLIENTS},scope:{type:"string",enum:["project","user"]},workspace:str,orchestrator:{type:"object",properties:{model:{const:"inherit"},recommendation:{type:"object",properties:{model:str,effort:str},required:["model"],additionalProperties:false}},required:["model"],additionalProperties:false},roles:{type:"object",properties:{routine:roleSchema,high:roleSchema,hard:roleSchema,advisor:roleSchema},required:["routine","high","hard","advisor"],additionalProperties:false},appTaskLane:{type:"object",properties:{enabled:{const:true}},required:["enabled"],additionalProperties:false}},["client","scope","workspace","orchestrator","roles"])},
  {name:"render_client_adapter",description:"Preview exact allowlisted native adapter paths and contents",inputSchema:objectSchema({workspace:str},["workspace"])},
  {name:"install_client_adapter",description:"Install only the confirmed exact preview",inputSchema:objectSchema({workspace:str,confirmationToken:str,userScopeConfirmationToken:str,hardConsentToken:str},["workspace","confirmationToken"])},
  {name:"uninstall_client_adapter",description:"Preview or confirm removal of exact managed files",inputSchema:objectSchema({confirmationToken:str})},
  {name:"resolve_route",description:"Fail-closed challenge-first route resolution from fresh single-use runtime evidence",inputSchema:objectSchema({taskClass:{type:"string",enum:["routine","medium","hard","planning","review"]},machineTier:{type:"string",enum:["default","fast"]},fastOverride:{type:"object",properties:{bounded:{const:true},oneRoute:{const:true}},required:["bounded","oneRoute"],additionalProperties:false},challenge:str,currentRuntimeEvidence:runtimeEvidenceSchema,targetRuntimeEvidence:runtimeEvidenceSchema},["taskClass"])},
  {name:"validate_configuration",description:"Validate setup and optionally renderability",inputSchema:objectSchema({workspace:str})},
  {name:"reset_configuration",description:"Reset logical configuration with exact confirmation",inputSchema:objectSchema({confirmationToken:str})}
];
export async function callTool(name:string,args:any={}) {
  const allowed:Record<string,string[]>={get_setup_status:[],get_preferences:[],save_preferences:["client","scope","workspace","orchestrator","roles","appTaskLane"],render_client_adapter:["workspace"],install_client_adapter:["workspace","confirmationToken","userScopeConfirmationToken","hardConsentToken"],uninstall_client_adapter:["confirmationToken"],resolve_route:["taskClass","machineTier","fastOverride","challenge","currentRuntimeEvidence","targetRuntimeEvidence"],validate_configuration:["workspace"],reset_configuration:["confirmationToken"]};
  if(!(name in allowed)) throw new Error(`unknown tool: ${name}`); rejectUnknown(args,allowed[name]!,name); recoverTransaction();
  if(name!=="save_preferences") for(const [key,value] of Object.entries(args)) if(typeof value==="string"&&/[\r\n\0]/.test(value)) throw new Error(`${key} contains control characters`);
  if(name==="get_setup_status") return configState();
  if(name==="get_preferences") { const s=configState(); if(s.status!=="ready") throw new Error(`setup is ${s.status}`); return s.preferences; }
  if(name==="save_preferences") return savePreferences(args);
  if(name==="render_client_adapter") { const s=configState(); if(s.status!=="ready") throw new Error(`setup is ${s.status}`); return renderAdapter(s.preferences!,args.workspace); }
  if(name==="install_client_adapter") return installAdapter(args);
  if(name==="uninstall_client_adapter") return uninstallAdapter(args);
  if(name==="resolve_route") return resolveRoute(args);
  if(name==="validate_configuration") { const s=configState(); return {status:s.status,valid:s.status==="ready",detail:s.detail,...(s.status==="ready"&&args.workspace?{preview:renderAdapter(s.preferences!,args.workspace)}:{})}; }
  if(name==="reset_configuration") return resetConfiguration(args);
  throw new Error(`unknown tool: ${name}`);
}
function response(id:unknown,result?:unknown,error?:unknown,code=-32000){ return error?{jsonrpc:"2.0",id,error:{code,message:error instanceof Error?error.message:String(error)}}:{jsonrpc:"2.0",id,result}; }
export async function handle(message:any){
  if(!message||message.jsonrpc!=="2.0"||typeof message.method!=="string"||("id" in (message??{}) && !["string","number"].includes(typeof message.id) && message.id!==null)) return response(message?.id??null,undefined,new Error("invalid JSON-RPC 2.0 request"),-32600);
  const notification=!("id" in message);
  if(message.method==="notifications/initialized") return null;
  if(notification) return null;
  if(message.method==="initialize") return response(message.id,{protocolVersion:"2025-03-26",capabilities:{tools:{}},serverInfo:{name:"sol-advisor",version:"0.6.0"}});
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
