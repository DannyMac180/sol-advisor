import { afterEach, beforeEach, describe, expect, setDefaultTimeout, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, unlinkSync, writeFileSync, existsSync, realpathSync, chmodSync, statSync, renameSync, readdirSync } from "node:fs";
import { dirname, join, parse } from "node:path";
import { homedir, tmpdir } from "node:os";
import { __resetDataPinForTests, __setManifestWriteFaultForTests, callTool, handle, renderAdapter } from "./server";

if(process.platform==="win32")setDefaultTimeout(30_000);
let root="", data="", workspace="";
const base=(client="codex",scope="project")=>({client,scope,workspace,orchestrator:{model:"inherit",recommendation:{model:"gpt-5.6-sol",effort:"high"}},roles:{routine:{model:"gpt-5.6-terra",...(client==="codex"||client==="cursor"?{effort:"high"}:{})},high:{model:"gpt-5.6-terra",...(client==="codex"||client==="cursor"?{effort:"high"}:{})},advisor:{model:"gpt-5.6-sol",...(client==="codex"||client==="cursor"?{effort:"high"}:{}),readonly:true}}});
const windowsRoot=process.env.SystemRoot??process.env.WINDIR??(process.env.SystemDrive?join(process.env.SystemDrive,"Windows"):join(parse(process.execPath).root,"Windows"));
const windowsPowerShell=join(windowsRoot,"System32","WindowsPowerShell","v1.0","powershell.exe");
const icacls=join(windowsRoot,"System32","icacls.exe");
const windowsUsersSid="*S-1-5-32-545";
function makePrivate(path:string){
 if(process.platform!=="win32"){chmodSync(path,0o700);return;}
 const sid=execFileSync(windowsPowerShell,["-NoLogo","-NoProfile","-NonInteractive","-Command","[Security.Principal.WindowsIdentity]::GetCurrent().User.Value"],{encoding:"utf8"}).trim();
 execFileSync(icacls,[path,"/inheritance:r","/grant:r",`*${sid}:(OI)(CI)F`,`*S-1-5-18:(OI)(CI)F`,`*S-1-5-32-544:(OI)(CI)F`]);
}
function makeNullDacl(path:string){
 execFileSync(windowsPowerShell,["-NoLogo","-NoProfile","-NonInteractive","-Command",'$security=[IO.Directory]::GetAccessControl($env:SOL_ADVISOR_ACL_PATH);$security.SetSecurityDescriptorSddlForm("D:NO_ACCESS_CONTROL",[Security.AccessControl.AccessControlSections]::Access);[IO.Directory]::SetAccessControl($env:SOL_ADVISOR_ACL_PATH,$security)'],{env:{...process.env,SOL_ADVISOR_ACL_PATH:path}});
}
beforeEach(()=>{__resetDataPinForTests();root=realpathSync(mkdtempSync(join(tmpdir(),"sol-advisor-test-")));data=join(root,"data");workspace=join(root,"work");mkdirSync(data);makePrivate(data);mkdirSync(workspace);process.env.PLUGIN_DATA=data;});
afterEach(()=>{__setManifestWriteFaultForTests(undefined);__resetDataPinForTests();delete process.env.PLUGIN_DATA;rmSync(root,{recursive:true,force:true});});

describe("MCP protocol",()=>{
 test("initialize ping and tools",async()=>{
  expect((await handle({jsonrpc:"2.0",id:1,method:"initialize",params:{protocolVersion:"x"}}))?.result.serverInfo.name).toBe("sol-advisor");
  expect((await handle({jsonrpc:"2.0",id:10,method:"initialize",params:{protocolVersion:"unknown-future"}}))?.result.protocolVersion).toBe("2025-03-26");
  expect((await handle({jsonrpc:"2.0",id:2,method:"ping"}))?.result).toEqual({});
  expect((await handle({jsonrpc:"2.0",id:3,method:"tools/list"}))?.result.tools).toHaveLength(8);
  expect((await handle({jsonrpc:"2.0",id:4,method:"nope"}))?.error.message).toContain("method not found");
  expect((await handle({jsonrpc:"2.0",id:5,method:"nope"}))?.error.code).toBe(-32601);
  expect((await handle({jsonrpc:"2.0",id:6,method:"tools/call",params:{}}))?.error.code).toBe(-32602);
  expect(await handle({jsonrpc:"2.0",method:"ping"})).toBeNull();
  const toolFailure:any=await handle({jsonrpc:"2.0",id:7,method:"tools/call",params:{name:"get_preferences",arguments:{}}});expect(toolFailure.error).toBeUndefined();expect(toolFailure.result.isError).toBe(true);
 });
 test("actual stdio server accepts newline-delimited JSON with a minimal PATH",async()=>{
  const env={...process.env,PATH:dirname(process.execPath),PLUGIN_DATA:data};delete env.SystemRoot;delete env.WINDIR;
  const proc=Bun.spawn([process.execPath,join(import.meta.dir,"server.ts")],{env,stdin:"pipe",stdout:"pipe",stderr:"pipe"});
  proc.stdin.write(JSON.stringify({jsonrpc:"2.0",id:1,method:"tools/call",params:{name:"get_setup_status",arguments:{}}})+"\n"); proc.stdin.end();
  const out=await new Response(proc.stdout).text(); expect(await proc.exited).toBe(0); expect(JSON.parse(out).result.structuredContent.status).toBe("missing");
 });
});

describe("PLUGIN_DATA boundary",()=>{
 test("rejects broad access and forbidden roots without changing permissions",async()=>{
  if(process.platform==="win32"){
   for(const sid of ["S-1-1-0","S-1-5-32-545","S-1-5-11"]){
    execFileSync(icacls,[data,"/grant",`*${sid}:(OI)(CI)R`]);
    try{await expect(callTool("get_setup_status")).rejects.toThrow("unapproved allow ACE");}
    finally{execFileSync(icacls,[data,"/remove:g",`*${sid}`]);makePrivate(data);}
    await callTool("get_setup_status");
   }
  }else{
   chmodSync(data,0o755);await expect(callTool("get_setup_status")).rejects.toThrow("must be private");expect(statSync(data).mode&0o777).toBe(0o755);chmodSync(data,0o700);await callTool("get_setup_status");
  }
  for(const bad of new Set(["/",parse(data).root,realpathSync(homedir()),realpathSync(join(import.meta.dir,".."))])){process.env.PLUGIN_DATA=bad;await expect(callTool("get_setup_status")).rejects.toThrow("cannot be");}
 });
 test("rejects a symlink ancestor before pinning PLUGIN_DATA",async()=>{
  const actual=join(root,"actual"),actualData=join(actual,"data");mkdirSync(actualData,{recursive:true});makePrivate(actualData);symlinkSync(actual,join(root,"linked"),process.platform==="win32"?"junction":"dir");process.env.PLUGIN_DATA=join(root,"linked","data");await expect(callTool("get_setup_status")).rejects.toThrow("symlink ancestor");process.env.PLUGIN_DATA=data;
 });
 test("pins PLUGIN_DATA device and inode for process lifetime",async()=>{
  await callTool("get_setup_status");renameSync(data,join(root,"old-data"));mkdirSync(data);makePrivate(data);await expect(callTool("get_setup_status")).rejects.toThrow("identity changed");
 });
 test("rejects a null Windows DACL",async()=>{
  if(process.platform!=="win32")return;
  makeNullDacl(data);
  try{await expect(callTool("get_setup_status")).rejects.toThrow("null DACL");}
  finally{makePrivate(data);}
  await expect(callTool("get_setup_status")).resolves.toBeTruthy();
 });
 test("rejects an unexpected Windows owner",async()=>{
  if(process.platform!=="win32")return;
  process.env.PLUGIN_DATA=realpathSync(join(windowsRoot,"System32"));
  try{await expect(callTool("get_setup_status")).rejects.toThrow("owner is outside the approved Windows principals");}
  finally{process.env.PLUGIN_DATA=data;}
 });
});

describe("configuration",()=>{
 test("missing corrupt old and ready states",async()=>{
  expect((await callTool("get_setup_status") as any).status).toBe("missing");
  mkdirSync(data,{recursive:true});writeFileSync(join(data,"config.json"),"{");expect((await callTool("get_setup_status") as any).status).toBe("corrupt");
  writeFileSync(join(data,"config.json"),JSON.stringify({schemaVersion:0}));expect((await callTool("get_setup_status") as any).status).toBe("schema-old");
  await callTool("save_preferences",base());expect((await callTool("get_setup_status") as any).status).toBe("ready");
 });
 test("rejects secrets and creates update backup",async()=>{
  await expect(callTool("save_preferences",{...base(),roles:{...(base() as any).roles,advisor:{...(base() as any).roles.advisor,token:"SECRET2"}}})).rejects.toThrow("forbidden");
  await callTool("save_preferences",base()); expect(readFileSync(join(data,"config.json"),"utf8")).not.toContain("SECRET");
  await callTool("save_preferences",base());expect(existsSync(join(data,"backups"))).toBe(true);
 });
 test("capability and fallback violations fail closed",async()=>{
  await expect(callTool("save_preferences",base("vscode") as any)).resolves.toBeTruthy();
  const bad:any=base("vscode");bad.roles.routine.effort="max";await expect(callTool("save_preferences",bad)).rejects.toThrow("cannot persist");
  const blank:any=base();blank.roles.high.model="";await expect(callTool("save_preferences",blank)).rejects.toThrow("exact");
  await expect(callTool("get_setup_status",{extra:true})).rejects.toThrow("unknown");
 });
 test("persists profiles by client scope and workspace",async()=>{
  await callTool("save_preferences",base("codex","project"));
  const other=join(root,"other");mkdirSync(other);await callTool("save_preferences",{...base("cursor","project"),workspace:other});
  const stored=JSON.parse(readFileSync(join(data,"config.json"),"utf8"));expect(Object.keys(stored.profiles)).toHaveLength(2);expect(stored.activeProfile).toContain("cursor:project:");
 });

 test("tampered persisted profiles with unknown fields fail closed",async()=>{
  await callTool("save_preferences",base());const path=join(data,"config.json"),stored=JSON.parse(readFileSync(path,"utf8"));stored.profiles[stored.activeProfile].roles.routine.apiToken="MUST_NOT_DISCLOSE";writeFileSync(path,JSON.stringify(stored));
  expect((await callTool("get_setup_status") as any).status).toBe("corrupt");await expect(callTool("get_preferences")).rejects.toThrow("corrupt");
 });
 test("confirmed reset purges config empty manifest and backups",async()=>{
  await callTool("save_preferences",base());await callTool("save_preferences",base());writeFileSync(join(data,"managed-files.json"),JSON.stringify({schemaVersion:1,files:[],updatedAt:"x"}));expect(existsSync(join(data,"backups"))).toBe(true);
  const out:any=await callTool("reset_configuration",{confirmationToken:"RESET SOL ADVISOR CONFIGURATION"});expect(out.purged).toBe(true);for(const name of ["config.json","managed-files.json","backups"])expect(existsSync(join(data,name))).toBe(false);
 });

 test("tampered recovery journal cannot mutate an arbitrary path",async()=>{
  await callTool("save_preferences",base());const stored=JSON.parse(readFileSync(join(data,"config.json"),"utf8")),sentinel=join(root,"sentinel");writeFileSync(sentinel,"KEEP");const journal={schemaVersion:1,operation:"install",phase:"targets-committed",committed:1,entries:[{target:sentinel,stage:join(root,"evil.stage"),newHash:"a".repeat(64),wasMissing:true}],manifestExisted:false,originalManifest:"",newManifest:"{}",profileKey:stored.activeProfile};writeFileSync(join(data,"transaction.json"),JSON.stringify(journal));await expect(callTool("get_setup_status")).rejects.toThrow("transaction journal");expect(readFileSync(sentinel,"utf8")).toBe("KEEP");expect(existsSync(join(data,"transaction.json"))).toBe(true);
 });

 test("preexisting backups symlink is rejected without external writes",async()=>{
  await callTool("save_preferences",base());const external=join(root,"external-backups");mkdirSync(external);symlinkSync(external,join(data,"backups"),process.platform==="win32"?"junction":"dir");await expect(callTool("save_preferences",base())).rejects.toThrow("backups must be a real directory");expect(existsSync(join(external,"config.json.bak"))).toBe(false);expect(readdirSync(external)).toHaveLength(0);
 });
 test("rejects a non-private backups directory",async()=>{
  await callTool("save_preferences",base());await callTool("save_preferences",base());const backups=join(data,"backups");
  if(process.platform==="win32")execFileSync(icacls,[backups,"/grant","*S-1-5-32-545:(OI)(CI)R"]);else chmodSync(backups,0o755);
  try{await expect(callTool("save_preferences",base())).rejects.toThrow("PLUGIN_DATA backups must be private");}
  finally{if(process.platform==="win32")execFileSync(icacls,[backups,"/remove:g","*S-1-5-32-545"]);makePrivate(backups);}
  await expect(callTool("save_preferences",base())).resolves.toBeTruthy();
 });
 test("rejects a broad ACL on an existing Windows config",async()=>{
  if(process.platform!=="win32")return;
  await callTool("save_preferences",base());
  const config=join(data,"config.json");
  execFileSync(icacls,[config,"/grant",`${windowsUsersSid}:R`]);
  try{const state:any=await callTool("get_setup_status");expect(state.status).toBe("corrupt");expect(state.detail).toContain("unapproved allow ACE");}
  finally{execFileSync(icacls,[config,"/remove:g",windowsUsersSid]);}
 });
 test("rejects a broad ACL on an existing Windows manifest",async()=>{
  if(process.platform!=="win32")return;
  await callTool("save_preferences",base());
  const manifest=join(data,"managed-files.json");
  writeFileSync(manifest,JSON.stringify({schemaVersion:1,files:[],updatedAt:new Date().toISOString()}));
  execFileSync(icacls,[manifest,"/grant",`${windowsUsersSid}:R`]);
  try{await expect(callTool("uninstall_client_adapter",{})).rejects.toThrow("unapproved allow ACE");}
  finally{execFileSync(icacls,[manifest,"/remove:g",windowsUsersSid]);}
 });
 test("rejects a broad ACL on an existing Windows journal",async()=>{
  if(process.platform!=="win32")return;
  const journal=join(data,"transaction.json");
  writeFileSync(journal,"{}");
  execFileSync(icacls,[journal,"/grant",`${windowsUsersSid}:R`]);
  try{await expect(callTool("get_setup_status")).rejects.toThrow("unapproved allow ACE");}
  finally{execFileSync(icacls,[journal,"/remove:g",windowsUsersSid]);unlinkSync(journal);}
 });
 test("rejects a broad ACL on an existing Windows backup",async()=>{
  if(process.platform!=="win32")return;
  await callTool("save_preferences",base());
  await callTool("save_preferences",base());
  const backups=join(data,"backups"),backup=join(backups,readdirSync(backups).find(name=>name.endsWith(".bak"))!);
  execFileSync(icacls,[backup,"/grant",`${windowsUsersSid}:R`]);
  try{await expect(callTool("save_preferences",base())).rejects.toThrow("unapproved allow ACE");}
  finally{execFileSync(icacls,[backup,"/remove:g",windowsUsersSid]);}
 },10_000);

});

describe("adapter rendering and lifecycle",()=>{
 test("renders every client and scope with deterministic exact paths",()=>{
  for(const client of ["codex","cursor","vscode","github-copilot","kiro"]){for(const scope of ["project","user"]){const p:any=base(client,scope);p.workspace=realpathSync(workspace);p.schemaVersion=1;p.profileKey=`${client}:${scope}:${workspace}`;p.fallbackPolicy="fail-closed";p.fallbacks=[];p.createdAt=p.updatedAt="x";p.pluginVersion="0.5.0";const a=renderAdapter(p,workspace);expect(a.files).toHaveLength(3);expect(a.files.every(f=>f.content.includes("sol-advisor-managed:v1"))).toBe(true);if(client==="cursor")expect(a.warnings.join(" ")).toContain("may fall back");expect(renderAdapter(p,workspace).planDigest).toBe(a.planDigest);}}
 });
 test("requires exact consent, refuses conflict, backs up updates, and uninstalls exact files",async()=>{
  await callTool("save_preferences",base());const preview:any=await callTool("render_client_adapter",{workspace});
  await expect(callTool("install_client_adapter",{workspace,confirmationToken:"yes"})).rejects.toThrow("exact unexpired");
  mkdirSync(join(workspace,".codex","agents"),{recursive:true});writeFileSync(preview.files[0].path,"mine");
  await expect(callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken})).rejects.toThrow("unchanged target state");rmSync(preview.files[0].path);
  const installed:any=await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});expect(installed.installed).toHaveLength(3);
  await callTool("save_preferences",{...base(),roles:{...(base() as any).roles,routine:{model:"gpt-5.6-terra-2",effort:"high"}}});const p2:any=await callTool("render_client_adapter",{workspace});const updated:any=await callTool("install_client_adapter",{workspace,confirmationToken:p2.confirmationToken});expect(updated.backups.length).toBe(3);
  const ask:any=await callTool("uninstall_client_adapter",{});expect(ask.requiresConfirmation).toBe(true);const gone:any=await callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken});expect(gone.removed).toHaveLength(3);expect(gone.removed.every((x:string)=>!existsSync(x))).toBe(true);
 });
 test("refuses traversal, symlink paths, and modified managed uninstall",async()=>{
  await callTool("save_preferences",base());await expect(callTool("render_client_adapter",{workspace:join(workspace,"..","missing")})).rejects.toThrow();
  mkdirSync(join(workspace,".codex"));symlinkSync(root,join(workspace,".codex","agents"),process.platform==="win32"?"junction":"dir");await expect(callTool("render_client_adapter",{workspace})).rejects.toThrow("symlink");
  unlinkSync(join(workspace,".codex","agents"));const preview:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});writeFileSync(preview.files[0].path,readFileSync(preview.files[0].path,"utf8")+"changed");const ask:any=await callTool("uninstall_client_adapter",{});await expect(callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken})).rejects.toThrow("changed");
 });
 test("user scope requires separate consent",async()=>{
  await callTool("save_preferences",base("codex","user"));const p:any=await callTool("render_client_adapter",{workspace});await expect(callTool("install_client_adapter",{workspace,confirmationToken:p.confirmationToken})).rejects.toThrow("separate exact user-scope");
 });
 test("preview nonce is one-time and reset refuses live installs",async()=>{
  await callTool("save_preferences",base());const p:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:p.confirmationToken});
  await expect(callTool("install_client_adapter",{workspace,confirmationToken:p.confirmationToken})).rejects.toThrow("one-time");
  await expect(callTool("reset_configuration",{confirmationToken:"RESET SOL ADVISOR CONFIGURATION"})).rejects.toThrow("uninstall");
 });



 test("install detects target swap before quarantine and restores the swapped file",async()=>{
  await callTool("save_preferences",base());let preview:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});await callTool("save_preferences",{...base(),roles:{...(base() as any).roles,routine:{model:"gpt-5.6-terra-updated",effort:"high"}}});preview=await callTool("render_client_adapter",{workspace});const target=preview.files[0].path,saved=`${target}.attacker-saved`;__setManifestWriteFaultForTests(point=>{if(point==="install-before-quarantine-1"){renameSync(target,saved);writeFileSync(target,"IMPOSTOR")}});await expect(callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken})).rejects.toThrow("quarantine identity/hash mismatch");expect(readFileSync(target,"utf8")).toBe("IMPOSTOR");expect(existsSync(saved)).toBe(true);expect(existsSync(join(data,"transaction.json"))).toBe(true);
 });
 test("uninstall detects target swap before quarantine and restores the swapped file",async()=>{
  await callTool("save_preferences",base());const preview:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});const ask:any=await callTool("uninstall_client_adapter",{}),target=preview.files[0].path,saved=`${target}.attacker-saved`;__setManifestWriteFaultForTests(point=>{if(point==="uninstall-before-quarantine-1"){renameSync(target,saved);writeFileSync(target,"IMPOSTOR")}});await expect(callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken})).rejects.toThrow("quarantine identity/hash mismatch");expect(readFileSync(target,"utf8")).toBe("IMPOSTOR");expect(existsSync(saved)).toBe(true);expect(existsSync(join(data,"transaction.json"))).toBe(true);
 });
 test("target appearing after preview is never clobbered",async()=>{
  await callTool("save_preferences",base());const preview:any=await callTool("render_client_adapter",{workspace});__setManifestWriteFaultForTests(point=>{if(point==="install-before-targets"){mkdirSync(join(workspace,".codex","agents"),{recursive:true});writeFileSync(preview.files[0].path,"ATTACKER")}});await expect(callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken})).rejects.toThrow("rollback incomplete");expect(readFileSync(preview.files[0].path,"utf8")).toBe("ATTACKER");expect(preview.files.slice(1).every((f:any)=>!existsSync(f.path))).toBe(true);
 });
 test("install faults after each target and manifest commit roll back zero partial mutation",async()=>{
  await callTool("save_preferences",base());for(const fault of ["install-target-1","install-target-2","install-target-3","install-manifest-commit"]){const preview:any=await callTool("render_client_adapter",{workspace});__setManifestWriteFaultForTests(point=>{if(point===fault)throw new Error(`injected ${fault}`)});await expect(callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken})).rejects.toThrow(fault);expect(preview.files.every((f:any)=>!existsSync(f.path))).toBe(true);expect(existsSync(join(data,"managed-files.json"))).toBe(false);expect(existsSync(join(data,"transaction.json"))).toBe(false);}
  __setManifestWriteFaultForTests(undefined);
 });
 test("uninstall faults quarantine transaction and restore all files",async()=>{
  await callTool("save_preferences",base());const preview:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});for(const fault of ["uninstall-target-1","uninstall-target-2","uninstall-target-3","uninstall-manifest-commit"]){const ask:any=await callTool("uninstall_client_adapter",{});__setManifestWriteFaultForTests(point=>{if(point===fault)throw new Error(`injected ${fault}`)});await expect(callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken})).rejects.toThrow(fault);for(const f of preview.files)expect(readFileSync(f.path,"utf8")).toBe(f.content);expect(JSON.parse(readFileSync(join(data,"managed-files.json"),"utf8")).files).toHaveLength(3);expect(existsSync(join(data,"transaction.json"))).toBe(false);}
  __setManifestWriteFaultForTests(undefined);
 });
 test("durable journal recovers simulated install and uninstall crashes",async()=>{
  await callTool("save_preferences",base());let preview:any=await callTool("render_client_adapter",{workspace});__setManifestWriteFaultForTests(point=>{if(point==="install-target-2")throw new Error("__SIMULATED_CRASH__")});await expect(callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken})).rejects.toThrow("SIMULATED_CRASH");expect(existsSync(join(data,"transaction.json"))).toBe(true);__setManifestWriteFaultForTests(undefined);expect((await callTool("get_setup_status") as any).status).toBe("ready");expect(preview.files.every((f:any)=>!existsSync(f.path))).toBe(true);
  preview=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});const ask:any=await callTool("uninstall_client_adapter",{});__setManifestWriteFaultForTests(point=>{if(point==="uninstall-target-2")throw new Error("__SIMULATED_CRASH__")});await expect(callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken})).rejects.toThrow("SIMULATED_CRASH");expect(existsSync(join(data,"transaction.json"))).toBe(true);__setManifestWriteFaultForTests(undefined);expect((await callTool("get_setup_status") as any).status).toBe("ready");for(const f of preview.files)expect(readFileSync(f.path,"utf8")).toBe(f.content);
 });

 test("cross-profile shared destination ownership fails closed",async()=>{
  await callTool("save_preferences",base("vscode"));const first:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:first.confirmationToken});
  await callTool("save_preferences",base("github-copilot"));const second:any=await callTool("render_client_adapter",{workspace});await expect(callTool("install_client_adapter",{workspace,confirmationToken:second.confirmationToken})).rejects.toThrow("different profile");
  const manifest=JSON.parse(readFileSync(join(data,"managed-files.json"),"utf8"));expect(new Set(manifest.files.map((f:any)=>f.path)).size).toBe(manifest.files.length);
 });

 test("duplicate manifest path ownership is rejected",async()=>{
  await callTool("save_preferences",base());const p:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:p.confirmationToken});const path=join(data,"managed-files.json"),manifest=JSON.parse(readFileSync(path,"utf8"));manifest.files.push({...manifest.files[0],profileKey:"other:profile"});writeFileSync(path,JSON.stringify(manifest));await expect(callTool("uninstall_client_adapter",{})).rejects.toThrow("duplicate path ownership");
 });

});
