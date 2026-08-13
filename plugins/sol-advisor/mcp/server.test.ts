import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync, existsSync, realpathSync, chmodSync, statSync, renameSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { __resetDataPinForTests, __setManifestWriteFaultForTests, __setRouteChallengeNowForTests, callTool, handle, renderAdapter } from "./server";

let root="", data="", workspace="";
const base=(client="codex",scope="project")=>({client,scope,workspace,orchestrator:{model:"inherit",recommendation:{model:"gpt-5.6-sol",effort:"high"}},roles:{routine:{model:"gpt-5.6-luna",...(client==="codex"||client==="cursor"?{effort:"max"}:{})},high:{model:"gpt-5.6-terra",...(client==="codex"||client==="cursor"?{effort:"high"}:{})},hard:{model:"gpt-5.6-sol",...(client==="codex"||client==="cursor"?{effort:"high"}:{})},advisor:{model:"gpt-5.6-sol",...(client==="codex"||client==="cursor"?{effort:"high"}:{}),readonly:true}}});
let evidenceSequence=0;
const threadId=()=>`00000000-0000-4000-8000-${String(++evidenceSequence).padStart(12,"0")}`;
let activeParentThreadId="";
const parentEvidence=(challenge:string,model:string,effort:string,sandboxPolicyType="danger-full-access",observedRuntimeTier:"default"|"priority"|null="default",overrides:any={})=>{const evidence={challenge,threadId:threadId(),parentThreadId:null,latestEventAt:new Date().toISOString(),evidenceSource:"codex-rollout-inspector" as const,executionContext:"parent" as const,agentIdentifier:null,model,effort,observedRuntimeTier,sandboxPolicyType,rawTokens:456,modelRounds:2,medianInputTokensPerRound:30,medianInputTokensFirst20:null,toolCalls:1,compactions:0,...overrides};activeParentThreadId=evidence.threadId;return evidence;};
const agentEvidence=(challenge:string,agentIdentifier:string,model:string,effort:string,sandboxPolicyType="danger-full-access",observedRuntimeTier:"default"|"priority"|null="default",overrides:any={})=>({challenge,threadId:threadId(),parentThreadId:activeParentThreadId,latestEventAt:new Date().toISOString(),evidenceSource:"codex-rollout-inspector" as const,executionContext:"agent" as const,agentIdentifier,model,effort,observedRuntimeTier,sandboxPolicyType,rawTokens:0,modelRounds:0,medianInputTokensPerRound:null,medianInputTokensFirst20:null,toolCalls:0,compactions:0,...overrides});
const challengeFor=async(taskClass:"routine"|"medium"|"hard"|"planning"|"review",extra:any={})=>{const result:any=await callTool("resolve_route",{taskClass,...extra});expect(result.evidenceStatus).toBe("challenge-required");return result.challenge as string;};
beforeEach(()=>{__resetDataPinForTests();evidenceSequence=0;activeParentThreadId="";root=realpathSync(mkdtempSync(join(tmpdir(),"sol-advisor-test-")));data=join(root,"data");workspace=join(root,"work");mkdirSync(data);chmodSync(data,0o700);mkdirSync(workspace);process.env.PLUGIN_DATA=data;});
afterEach(()=>{__setManifestWriteFaultForTests(undefined);__setRouteChallengeNowForTests(undefined);__resetDataPinForTests();delete process.env.PLUGIN_DATA;rmSync(root,{recursive:true,force:true});});

describe("MCP protocol",()=>{
 test("initialize ping and tools",async()=>{
  expect((await handle({jsonrpc:"2.0",id:1,method:"initialize",params:{protocolVersion:"x"}}))?.result.serverInfo.name).toBe("sol-advisor");
  expect((await handle({jsonrpc:"2.0",id:10,method:"initialize",params:{protocolVersion:"unknown-future"}}))?.result.protocolVersion).toBe("2025-03-26");
  expect((await handle({jsonrpc:"2.0",id:2,method:"ping"}))?.result).toEqual({});
  expect((await handle({jsonrpc:"2.0",id:3,method:"tools/list"}))?.result.tools).toHaveLength(9);
  expect((await handle({jsonrpc:"2.0",id:4,method:"nope"}))?.error.message).toContain("method not found");
  expect((await handle({jsonrpc:"2.0",id:5,method:"nope"}))?.error.code).toBe(-32601);
  expect((await handle({jsonrpc:"2.0",id:6,method:"tools/call",params:{}}))?.error.code).toBe(-32602);
  expect(await handle({jsonrpc:"2.0",method:"ping"})).toBeNull();
  const toolFailure:any=await handle({jsonrpc:"2.0",id:7,method:"tools/call",params:{name:"get_preferences",arguments:{}}});expect(toolFailure.error).toBeUndefined();expect(toolFailure.result.isError).toBe(true);
 });
 test("actual stdio server accepts newline-delimited JSON",async()=>{
  const proc=Bun.spawn(["bun",join(import.meta.dir,"server.ts")],{env:{...process.env,PLUGIN_DATA:data},stdin:"pipe",stdout:"pipe",stderr:"pipe"});
  proc.stdin.write(JSON.stringify({jsonrpc:"2.0",id:1,method:"ping"})+"\n"); proc.stdin.end();
  const out=await new Response(proc.stdout).text(); expect(await proc.exited).toBe(0); expect(JSON.parse(out).result).toEqual({});
 });
});

describe("PLUGIN_DATA boundary",()=>{
 test("rejects root home plugin root and symlink ancestors without chmod",async()=>{
  chmodSync(data,0o755);await expect(callTool("get_setup_status")).rejects.toThrow("must be private");expect(statSync(data).mode&0o777).toBe(0o755);chmodSync(data,0o700);await callTool("get_setup_status");
  for(const bad of ["/",realpathSync(process.env.HOME!),realpathSync(join(import.meta.dir,".."))]){process.env.PLUGIN_DATA=bad;await expect(callTool("get_setup_status")).rejects.toThrow("cannot be");}
  const actual=join(root,"actual");mkdirSync(join(actual,"data"),{recursive:true});symlinkSync(actual,join(root,"linked"));process.env.PLUGIN_DATA=join(root,"linked","data");await expect(callTool("get_setup_status")).rejects.toThrow("symlink ancestor");process.env.PLUGIN_DATA=data;
 });
 test("pins PLUGIN_DATA device and inode for process lifetime",async()=>{
  await callTool("get_setup_status");renameSync(data,join(root,"old-data"));mkdirSync(data);chmodSync(data,0o700);await expect(callTool("get_setup_status")).rejects.toThrow("identity changed");
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
  await callTool("save_preferences",base());const external=join(root,"external-backups");mkdirSync(external);symlinkSync(external,join(data,"backups"));await expect(callTool("save_preferences",base())).rejects.toThrow("backups must be a real directory");expect(existsSync(join(external,"config.json.bak"))).toBe(false);expect(readdirSync(external)).toHaveLength(0);
 });
 test("atomically migrates v1 profiles once and leaves hard pending consent",async()=>{
  const old:any=base();delete old.roles.hard;
  const profileKey=`codex:project:${workspace}`,legacy={schemaVersion:1,client:"codex",scope:"project",workspace,orchestrator:old.orchestrator,roles:old.roles,fallbackPolicy:"fail-closed",fallbacks:[],profileKey,createdAt:"x",updatedAt:"x",pluginVersion:"0.5.0"};
  writeFileSync(join(data,"config.json"),JSON.stringify({schemaVersion:1,activeProfile:profileKey,profiles:{[profileKey]:legacy}}));
  expect((await callTool("get_setup_status") as any).status).toBe("ready");
  const migrated=JSON.parse(readFileSync(join(data,"config.json"),"utf8"));expect(migrated.schemaVersion).toBe(2);expect(migrated.profiles[profileKey].roles.hard).toMatchObject({model:"gpt-5.6-sol",effort:"high",machineTier:"default"});expect(migrated.profiles[profileKey].hardRoute.status).toBe("pending-consent");
  const once=readFileSync(join(data,"config.json"),"utf8");await callTool("get_setup_status");expect(readFileSync(join(data,"config.json"),"utf8")).toBe(once);
 });
 test("keeps a recorded v0.5 three-file adapter exactly uninstallable after migration",async()=>{
  const old:any=base();delete old.roles.hard;const profileKey=`codex:project:${workspace}`,legacy={schemaVersion:1,client:"codex",scope:"project",workspace,orchestrator:old.orchestrator,roles:old.roles,fallbackPolicy:"fail-closed",fallbacks:[],profileKey,createdAt:"x",updatedAt:"x",pluginVersion:"0.5.0"};
  writeFileSync(join(data,"config.json"),JSON.stringify({schemaVersion:1,activeProfile:profileKey,profiles:{[profileKey]:legacy}}));await callTool("get_setup_status");
  const names=["routine","high","advisor"],dir=join(workspace,".codex","agents");mkdirSync(dir,{recursive:true});const files=names.map(name=>{const path=join(dir,`sol-advisor-${name}.toml`),content=`# sol-advisor-managed:v1\nlegacy-${name}\n`;writeFileSync(path,content);return {profileKey,path,hash:new Bun.CryptoHasher("sha256").update(content).digest("hex")};});writeFileSync(join(data,"managed-files.json"),JSON.stringify({schemaVersion:1,files,updatedAt:"x"}));
  const ask:any=await callTool("uninstall_client_adapter",{});const removed:any=await callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken});expect(removed.removed).toHaveLength(3);expect(files.every(file=>!existsSync(file.path))).toBe(true);
 });
 test("requires migrated hard consent and fresh exact runtime evidence",async()=>{
  const old:any=base();delete old.roles.hard;const profileKey=`codex:project:${workspace}`,legacy={schemaVersion:1,client:"codex",scope:"project",workspace,orchestrator:old.orchestrator,roles:old.roles,fallbackPolicy:"fail-closed",fallbacks:[],profileKey,createdAt:"x",updatedAt:"x",pluginVersion:"0.5.0"};
  writeFileSync(join(data,"config.json"),JSON.stringify({schemaVersion:1,activeProfile:profileKey,profiles:{[profileKey]:legacy}}));await callTool("get_setup_status");await callTool("save_preferences",base());expect((await callTool("get_preferences") as any).hardRoute.status).toBe("pending-consent");const preview:any=await callTool("render_client_adapter",{workspace});
  const pendingChallenge=await challengeFor("hard");expect((await callTool("resolve_route",{taskClass:"hard",challenge:pendingChallenge,currentRuntimeEvidence:parentEvidence(pendingChallenge,"gpt-5.6-sol","high")}) as any).blockedReason).toContain("pending four-role preview consent");
  await expect(callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken})).rejects.toThrow("hard consent");
  await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken,hardConsentToken:preview.hardConsentToken});
  const challenge=await challengeFor("hard"),current=parentEvidence(challenge,"gpt-5.6-sol","high"),wrongTarget=agentEvidence(challenge,"sol_advisor_hard","gpt-5.6-sol","max");
  await callTool("save_preferences",base());expect((await callTool("get_preferences") as any).hardRoute.status).toBe("runtime-pending");
  expect((await callTool("resolve_route",{taskClass:"hard",challenge,currentRuntimeEvidence:current}) as any).evidenceStatus).toBe("spawn-required");
  expect((await callTool("resolve_route",{taskClass:"hard",challenge,currentRuntimeEvidence:current,targetRuntimeEvidence:wrongTarget}) as any).evidenceStatus).toBe("blocked");expect((await callTool("get_preferences") as any).hardRoute.status).toBe("runtime-pending");
  await expect(callTool("resolve_route",{taskClass:"hard",challenge,currentRuntimeEvidence:current,targetRuntimeEvidence:wrongTarget})).rejects.toThrow("already consumed");expect((await callTool("get_preferences") as any).hardRoute.status).toBe("runtime-pending");
  const freshChallenge=await challengeFor("hard"),freshCurrent=parentEvidence(freshChallenge,"gpt-5.6-sol","high"),freshTarget=agentEvidence(freshChallenge,"sol_advisor_hard","gpt-5.6-sol","high");expect((await callTool("resolve_route",{taskClass:"hard",challenge:freshChallenge,currentRuntimeEvidence:freshCurrent,targetRuntimeEvidence:freshTarget}) as any).evidenceStatus).toBe("verified");expect((await callTool("get_preferences") as any).hardRoute.status).toBe("ready");expect(readdirSync(join(data,"backups")).some(name=>name.endsWith("-config.json.bak"))).toBe(true);
  const parentChallenge=await challengeFor("hard");expect((await callTool("resolve_route",{taskClass:"hard",challenge:parentChallenge,currentRuntimeEvidence:parentEvidence(parentChallenge,"gpt-5.6-sol","high")}) as any).executionPlacement).toBe("parent");
 });
 test("recovers a real exact three-role v0.5 uninstall crash journal after migration",async()=>{
  const old:any=base();delete old.roles.hard;const profileKey=`codex:project:${workspace}`,legacy={schemaVersion:1,client:"codex",scope:"project",workspace,orchestrator:old.orchestrator,roles:old.roles,fallbackPolicy:"fail-closed",fallbacks:[],profileKey,createdAt:"x",updatedAt:"x",pluginVersion:"0.5.0"};
  writeFileSync(join(data,"config.json"),JSON.stringify({schemaVersion:1,activeProfile:profileKey,profiles:{[profileKey]:legacy}}));await callTool("get_setup_status");const dir=join(workspace,".codex","agents");mkdirSync(dir,{recursive:true});const files=["routine","high","advisor"].map(name=>{const path=join(dir,`sol-advisor-${name}.toml`),content=`# sol-advisor-managed:v1\nlegacy-${name}\n`;writeFileSync(path,content);return {profileKey,path,hash:new Bun.CryptoHasher("sha256").update(content).digest("hex"),content};});writeFileSync(join(data,"managed-files.json"),JSON.stringify({schemaVersion:1,files:files.map(({content,...file})=>file),updatedAt:"x"}));
  const ask:any=await callTool("uninstall_client_adapter",{});__setManifestWriteFaultForTests(point=>{if(point==="uninstall-target-2")throw new Error("__SIMULATED_CRASH__")});await expect(callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken})).rejects.toThrow("SIMULATED_CRASH");expect(existsSync(join(data,"transaction.json"))).toBe(true);__setManifestWriteFaultForTests(undefined);expect((await callTool("get_setup_status") as any).status).toBe("ready");for(const file of files)expect(readFileSync(file.path,"utf8")).toBe(file.content);expect(JSON.parse(readFileSync(join(data,"managed-files.json"),"utf8")).files).toHaveLength(3);
 });

});

describe("route resolution",()=>{
 test("issues a task/profile/tier-bound challenge before it selects a route",async()=>{
  await callTool("save_preferences",base());const issued:any=await callTool("resolve_route",{taskClass:"routine"});expect(issued).toMatchObject({evidenceStatus:"challenge-required",forkContext:false,parallelism:1});expect("executionPlacement" in issued).toBe(false);expect("storageRole" in issued).toBe(false);expect(issued.challenge).toMatch(/^[0-9a-f-]{36}$/);
  await expect(callTool("resolve_route",{taskClass:"hard",challenge:issued.challenge,currentRuntimeEvidence:parentEvidence(issued.challenge,"gpt-5.6-luna","max")})).rejects.toThrow("does not match this task");
 });
 test("consumes exact parent proof, preserves a fresh-agent challenge, and rejects replay",async()=>{
  await callTool("save_preferences",base());const routineChallenge=await challengeFor("routine"),routineEvidence=parentEvidence(routineChallenge,"gpt-5.6-luna","max");
  const routine:any=await callTool("resolve_route",{taskClass:"routine",challenge:routineChallenge,currentRuntimeEvidence:routineEvidence});expect(routine).toMatchObject({executionPlacement:"parent",evidenceStatus:"verified",escalated:false,savedMachineTier:"default",observedRuntimeTier:"default"});
  await expect(callTool("resolve_route",{taskClass:"routine",challenge:routineChallenge,currentRuntimeEvidence:routineEvidence})).rejects.toThrow("already consumed");
  await challengeFor("routine");await expect(callTool("resolve_route",{taskClass:"routine",challenge:routineChallenge,currentRuntimeEvidence:routineEvidence})).rejects.toThrow("unknown");
  const hardChallenge=await challengeFor("hard"),current=parentEvidence(hardChallenge,"gpt-5.6-luna","max");const changed:any=await callTool("resolve_route",{taskClass:"hard",challenge:hardChallenge,currentRuntimeEvidence:current});expect(changed).toMatchObject({executionPlacement:"fresh_agent",evidenceStatus:"spawn-required",escalated:true,challenge:hardChallenge});
  const hard:any=await callTool("resolve_route",{taskClass:"hard",challenge:hardChallenge,currentRuntimeEvidence:current,targetRuntimeEvidence:agentEvidence(hardChallenge,"sol_advisor_hard","gpt-5.6-sol","high")});expect(hard).toMatchObject({evidenceStatus:"verified",executionPlacement:"fresh_agent",escalated:true});
  const reviewChallenge=await challengeFor("review");const review:any=await callTool("resolve_route",{taskClass:"review",challenge:reviewChallenge,currentRuntimeEvidence:parentEvidence(reviewChallenge,"gpt-5.6-sol","high","read-only")});expect(review).toMatchObject({executionPlacement:"fresh_agent",evidenceStatus:"spawn-required",escalated:true,challenge:reviewChallenge});
 });
 test("rejects expired, stale-parent, pre-issuance target, future, same-thread, secret, and unknown runtime evidence",async()=>{
  await callTool("save_preferences",base());const expirationStart=Date.now(),expiredChallenge=await challengeFor("routine");__setRouteChallengeNowForTests(()=>expirationStart+301_000);await expect(callTool("resolve_route",{taskClass:"routine",challenge:expiredChallenge,currentRuntimeEvidence:parentEvidence(expiredChallenge,"gpt-5.6-luna","max","danger-full-access","default",{latestEventAt:new Date(expirationStart).toISOString()})})).rejects.toThrow("expired");await challengeFor("routine");await expect(callTool("resolve_route",{taskClass:"routine",challenge:expiredChallenge,currentRuntimeEvidence:parentEvidence(expiredChallenge,"gpt-5.6-luna","max","danger-full-access","default",{latestEventAt:new Date(expirationStart).toISOString()})})).rejects.toThrow("unknown");const clock=Date.parse("2026-08-13T12:00:00Z");__setRouteChallengeNowForTests(()=>clock);
  const recentChallenge=await challengeFor("routine"),recentParent=parentEvidence(recentChallenge,"gpt-5.6-luna","max","danger-full-access","default",{latestEventAt:new Date(clock-1).toISOString()});expect((await callTool("resolve_route",{taskClass:"routine",challenge:recentChallenge,currentRuntimeEvidence:recentParent}) as any).evidenceStatus).toBe("verified");await expect(callTool("resolve_route",{taskClass:"routine",challenge:recentChallenge,currentRuntimeEvidence:recentParent})).rejects.toThrow("already consumed");
  const staleChallenge=await challengeFor("routine"),staleParent=parentEvidence(staleChallenge,"gpt-5.6-luna","max","danger-full-access","default",{latestEventAt:new Date(clock-300_001).toISOString()});await expect(callTool("resolve_route",{taskClass:"routine",challenge:staleChallenge,currentRuntimeEvidence:staleParent})).rejects.toThrow("five-minute current-parent evidence age");expect((await callTool("resolve_route",{taskClass:"routine",challenge:staleChallenge,currentRuntimeEvidence:{...staleParent,latestEventAt:new Date(clock-300_000).toISOString()}}) as any).evidenceStatus).toBe("verified");
  const targetChallenge=await challengeFor("hard"),targetCurrent=parentEvidence(targetChallenge,"gpt-5.6-luna","max","danger-full-access","default",{latestEventAt:new Date(clock).toISOString()}),preIssuanceTarget=agentEvidence(targetChallenge,"sol_advisor_hard","gpt-5.6-sol","high","danger-full-access","default",{latestEventAt:new Date(clock-1).toISOString()});await expect(callTool("resolve_route",{taskClass:"hard",challenge:targetChallenge,currentRuntimeEvidence:targetCurrent,targetRuntimeEvidence:preIssuanceTarget})).rejects.toThrow("at or after challenge issuance");expect((await callTool("resolve_route",{taskClass:"hard",challenge:targetChallenge,currentRuntimeEvidence:targetCurrent,targetRuntimeEvidence:{...preIssuanceTarget,latestEventAt:new Date(clock).toISOString()}}) as any).evidenceStatus).toBe("verified");
  const futureChallenge=await challengeFor("routine"),futureParent=parentEvidence(futureChallenge,"gpt-5.6-luna","max","danger-full-access","default",{latestEventAt:new Date(clock+5_001).toISOString()});await expect(callTool("resolve_route",{taskClass:"routine",challenge:futureChallenge,currentRuntimeEvidence:futureParent})).rejects.toThrow("future-clock skew");expect((await callTool("resolve_route",{taskClass:"routine",challenge:futureChallenge,currentRuntimeEvidence:{...futureParent,latestEventAt:new Date(clock).toISOString()}}) as any).evidenceStatus).toBe("verified");__setRouteChallengeNowForTests(undefined);
  const sameThreadChallenge=await challengeFor("hard"),current=parentEvidence(sameThreadChallenge,"gpt-5.6-luna","max"),target=agentEvidence(sameThreadChallenge,"sol_advisor_hard","gpt-5.6-sol","high","danger-full-access","default",{threadId:current.threadId});expect((await callTool("resolve_route",{taskClass:"hard",challenge:sameThreadChallenge,currentRuntimeEvidence:current,targetRuntimeEvidence:target}) as any).blockedReason).toContain("different thread IDs");await expect(callTool("resolve_route",{taskClass:"hard",challenge:sameThreadChallenge,currentRuntimeEvidence:current,targetRuntimeEvidence:target})).rejects.toThrow("already consumed");
  const unknownChallenge=await challengeFor("routine");await expect(callTool("resolve_route",{taskClass:"routine",challenge:unknownChallenge,currentRuntimeEvidence:{...parentEvidence(unknownChallenge,"gpt-5.6-luna","max"),extra:"no"}})).rejects.toThrow("unknown");await expect(callTool("resolve_route",{taskClass:"routine",challenge:unknownChallenge,currentRuntimeEvidence:{...parentEvidence(unknownChallenge,"gpt-5.6-luna","max"),apiToken:"no"}})).rejects.toThrow("forbidden");
 });
 test("consumes challenges on blocked current or target provenance",async()=>{
  await callTool("save_preferences",base());const currentChallenge=await challengeFor("routine"),badCurrent=parentEvidence(currentChallenge,"gpt-5.6-luna","max","danger-full-access","default",{executionContext:"agent",agentIdentifier:"sol_advisor_routine"});expect((await callTool("resolve_route",{taskClass:"routine",challenge:currentChallenge,currentRuntimeEvidence:badCurrent}) as any).blockedReason).toContain("current runtime evidence provenance");await expect(callTool("resolve_route",{taskClass:"routine",challenge:currentChallenge,currentRuntimeEvidence:badCurrent})).rejects.toThrow("already consumed");
  const targetChallenge=await challengeFor("hard"),current=parentEvidence(targetChallenge,"gpt-5.6-luna","max"),badTarget=agentEvidence(targetChallenge,"sol_advisor_hard","gpt-5.6-sol","high","danger-full-access","default",{executionContext:"parent",agentIdentifier:null});expect((await callTool("resolve_route",{taskClass:"hard",challenge:targetChallenge,currentRuntimeEvidence:current,targetRuntimeEvidence:badTarget}) as any).blockedReason).toContain("target runtime evidence provenance");await expect(callTool("resolve_route",{taskClass:"hard",challenge:targetChallenge,currentRuntimeEvidence:current,targetRuntimeEvidence:badTarget})).rejects.toThrow("already consumed");
 });
 test("issues challenges before Fast or missing-effort policy disclosure",async()=>{
  await callTool("save_preferences",base());const first:any=await callTool("resolve_route",{taskClass:"routine",machineTier:"fast"});expect(first).toMatchObject({evidenceStatus:"challenge-required",blockedReason:null});expect("storageRole" in first).toBe(false);expect("configured" in first).toBe(false);
  const blocked:any=await callTool("resolve_route",{taskClass:"routine",machineTier:"fast",challenge:first.challenge,currentRuntimeEvidence:parentEvidence(first.challenge,"gpt-5.6-luna","max")});expect(blocked.blockedReason).toContain("bounded");
  const priorityChallenge=await challengeFor("routine",{machineTier:"fast",fastOverride:{bounded:true,oneRoute:true}});expect((await callTool("resolve_route",{taskClass:"routine",machineTier:"fast",fastOverride:{bounded:true,oneRoute:true},challenge:priorityChallenge,currentRuntimeEvidence:parentEvidence(priorityChallenge,"gpt-5.6-luna","max","danger-full-access",null)}) as any).evidenceStatus).toBe("spawn-required");
  const fastChallenge=await challengeFor("routine",{machineTier:"fast",fastOverride:{bounded:true,oneRoute:true}});expect((await callTool("resolve_route",{taskClass:"routine",machineTier:"fast",fastOverride:{bounded:true,oneRoute:true},challenge:fastChallenge,currentRuntimeEvidence:parentEvidence(fastChallenge,"gpt-5.6-luna","max","danger-full-access","priority")}) as any).budget.toolCalls).toBe(10);
 });
 test("keeps cross-client model-only adapters fail-closed on unsupported effort evidence",async()=>{
  await callTool("save_preferences",base("vscode"));const preview:any=await callTool("render_client_adapter",{workspace});expect(preview.files).toHaveLength(4);
  const route:any=await callTool("resolve_route",{taskClass:"routine"});
  expect(route).toMatchObject({evidenceStatus:"challenge-required",blockedReason:null});const blocked:any=await callTool("resolve_route",{taskClass:"routine",challenge:route.challenge,currentRuntimeEvidence:parentEvidence(route.challenge,"gpt-5.6-luna","max")});expect(blocked).toMatchObject({evidenceStatus:"blocked",blockedReason:"configured effort is unavailable"});
 });
 test("keeps selected tiers, planning budget, and writable sandbox evidence distinct",async()=>{
  await callTool("save_preferences",base());const planningChallenge=await challengeFor("planning"),planning:any=await callTool("resolve_route",{taskClass:"planning",challenge:planningChallenge,currentRuntimeEvidence:parentEvidence(planningChallenge,"gpt-5.6-sol","high","read-only")});expect(planning).toMatchObject({executionPlacement:"parent",requestedMachineTier:"default",requestedRuntimeTier:"default",savedMachineTier:"default",observedRuntimeTier:"default",budget:{toolCalls:25,rawTokens:2_500_000,compactions:0}});
  const hardChallenge=await challengeFor("hard"),hardCurrent=parentEvidence(hardChallenge,"gpt-5.6-luna","max","danger-full-access","priority"),fresh:any=await callTool("resolve_route",{taskClass:"hard",challenge:hardChallenge,currentRuntimeEvidence:hardCurrent,targetRuntimeEvidence:agentEvidence(hardChallenge,"sol_advisor_hard","gpt-5.6-sol","high","danger-full-access","default")});expect(fresh.observedRuntimeTier).toBe("default");const readonlyChallenge=await challengeFor("routine"),writableReadonly:any=await callTool("resolve_route",{taskClass:"routine",challenge:readonlyChallenge,currentRuntimeEvidence:parentEvidence(readonlyChallenge,"gpt-5.6-luna","max","read-only")});expect(writableReadonly.evidenceStatus).toBe("spawn-required");
 });
 test("accepts a recent pre-challenge parent shell-inspector object without translation",async()=>{
  const issuedAt=Date.parse("2026-08-13T12:00:00Z"),parentContextAt=new Date(issuedAt-1_000).toISOString();__setRouteChallengeNowForTests(()=>issuedAt);await callTool("save_preferences",base());const fixtureThread="11111111-1111-7111-8111-111111111111",runtimeHome=join(root,"runtime-home"),rollout=join(runtimeHome,"sessions","2026","08","13",`rollout-2026-08-13T00-00-00-${fixtureThread}.jsonl`);mkdirSync(join(runtimeHome,"sessions","2026","08","13"),{recursive:true});writeFileSync(rollout,[
   {timestamp:parentContextAt,type:"session_meta",payload:{id:fixtureThread}},
   {timestamp:parentContextAt,type:"turn_context",payload:{model:"gpt-5.6-luna",effort:"max",sandbox_policy:{type:"danger-full-access"}}},
   {timestamp:parentContextAt,type:"event_msg",payload:{type:"thread_settings_applied",thread_settings:{service_tier:"default"}}},
   {timestamp:parentContextAt,type:"event_msg",payload:{type:"token_count",info:{total_token_usage:{total_tokens:456},last_token_usage:{input_tokens:30}}}},
   {timestamp:parentContextAt,type:"response_item",payload:{type:"custom_tool_call"}}
  ].map(record=>JSON.stringify(record)).join("\n")+"\n");const challenge=await challengeFor("routine"),inspector=Bun.spawn(["sh",join(import.meta.dir,"..","scripts","inspect-agent-runtime.sh"),"--challenge",challenge,fixtureThread],{env:{...process.env,CODEX_HOME:runtimeHome},stdout:"pipe",stderr:"pipe"}),output=await new Response(inspector.stdout).text(),error=await new Response(inspector.stderr).text(),exit=await inspector.exited;if(exit!==0)throw new Error(error);const evidence=JSON.parse(output);expect(Object.keys(evidence).sort()).toEqual(["agentIdentifier","challenge","compactions","effort","evidenceSource","executionContext","latestEventAt","medianInputTokensFirst20","medianInputTokensPerRound","model","modelRounds","observedRuntimeTier","parentThreadId","rawTokens","sandboxPolicyType","threadId","toolCalls"].sort());expect(evidence.parentThreadId).toBeNull();expect(evidence.latestEventAt).toBe(parentContextAt);const route:any=await callTool("resolve_route",{taskClass:"routine",challenge,currentRuntimeEvidence:evidence});expect(route).toMatchObject({evidenceStatus:"verified",executionPlacement:"parent",observedRuntimeTier:"default"});
 });
 test("binds shell-inspector target evidence to its exact parent and rejects unrelated parent IDs",async()=>{
  await callTool("save_preferences",base());const challenge=await challengeFor("hard"),parentId="11111111-1111-7111-8111-111111111111",agentId="22222222-2222-7222-8222-222222222222",runtimeHome=join(root,"bound-runtime"),dir=join(runtimeHome,"sessions","2026","08","13"),at=new Date().toISOString();mkdirSync(dir,{recursive:true});
  writeFileSync(join(dir,`rollout-parent-${parentId}.jsonl`),[{timestamp:at,type:"session_meta",payload:{id:parentId}},{timestamp:at,type:"turn_context",payload:{model:"gpt-5.6-luna",effort:"max",sandbox_policy:{type:"danger-full-access"}}}].map(JSON.stringify).join("\n")+"\n");
  writeFileSync(join(dir,`rollout-agent-${agentId}.jsonl`),[{timestamp:at,type:"session_meta",payload:{id:agentId,parent_thread_id:parentId,agent_role:"sol_advisor_hard"}},{timestamp:at,type:"turn_context",payload:{model:"gpt-5.6-sol",effort:"high",sandbox_policy:{type:"danger-full-access"}}}].map(JSON.stringify).join("\n")+"\n");
  const inspect=async(id:string)=>{const child=Bun.spawn(["sh",join(import.meta.dir,"..","scripts","inspect-agent-runtime.sh"),"--challenge",challenge,id],{env:{...process.env,CODEX_HOME:runtimeHome},stdout:"pipe"});const output=await new Response(child.stdout).text();expect(await child.exited).toBe(0);return JSON.parse(output);};const current=await inspect(parentId),target=await inspect(agentId);expect(current.parentThreadId).toBeNull();expect(target.parentThreadId).toBe(parentId);expect((await callTool("resolve_route",{taskClass:"hard",challenge,currentRuntimeEvidence:current,targetRuntimeEvidence:target}) as any).evidenceStatus).toBe("verified");
  const rejectedChallenge=await challengeFor("hard"),rejectedCurrent={...current,challenge:rejectedChallenge,latestEventAt:new Date().toISOString()},rejectedTarget={...target,challenge:rejectedChallenge,parentThreadId:"33333333-3333-7333-8333-333333333333",latestEventAt:new Date().toISOString()};expect((await callTool("resolve_route",{taskClass:"hard",challenge:rejectedChallenge,currentRuntimeEvidence:rejectedCurrent,targetRuntimeEvidence:rejectedTarget}) as any).blockedReason).toContain("exact current parent thread");
 });
});

describe("adapter rendering and lifecycle",()=>{
 test("renders every client and scope with deterministic exact paths",()=>{
  for(const client of ["codex","cursor","vscode","github-copilot","kiro"]){for(const scope of ["project","user"]){const p:any=base(client,scope);p.workspace=realpathSync(workspace);p.schemaVersion=2;p.profileKey=`${client}:${scope}:${workspace}`;p.fallbackPolicy="fail-closed";p.fallbacks=[];p.hardRoute={status:"ready"};p.createdAt=p.updatedAt="x";p.pluginVersion="0.6.0";for(const role of Object.values(p.roles) as any[])role.machineTier="default";const a=renderAdapter(p,workspace);expect(a.files).toHaveLength(4);expect(a.files.every(f=>f.content.includes("sol-advisor-managed:v1"))).toBe(true);if(client==="cursor")expect(a.warnings.join(" ")).toContain("may fall back");expect(renderAdapter(p,workspace).planDigest).toBe(a.planDigest);}}
 });
 test("requires exact consent, refuses conflict, backs up updates, and uninstalls exact files",async()=>{
  await callTool("save_preferences",base());const preview:any=await callTool("render_client_adapter",{workspace});
  await expect(callTool("install_client_adapter",{workspace,confirmationToken:"yes"})).rejects.toThrow("exact unexpired");
  mkdirSync(join(workspace,".codex","agents"),{recursive:true});writeFileSync(preview.files[0].path,"mine");
  await expect(callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken})).rejects.toThrow("unchanged target state");rmSync(preview.files[0].path);
  const installed:any=await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});expect(installed.installed).toHaveLength(4);
  await callTool("save_preferences",{...base(),roles:{...(base() as any).roles,routine:{model:"gpt-5.6-terra-2",effort:"high"}}});const p2:any=await callTool("render_client_adapter",{workspace});const updated:any=await callTool("install_client_adapter",{workspace,confirmationToken:p2.confirmationToken});expect(updated.backups.length).toBe(4);
  const ask:any=await callTool("uninstall_client_adapter",{});expect(ask.requiresConfirmation).toBe(true);const gone:any=await callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken});expect(gone.removed).toHaveLength(4);expect(gone.removed.every((x:string)=>!existsSync(x))).toBe(true);
 });
 test("refuses traversal, symlink paths, and modified managed uninstall",async()=>{
  await callTool("save_preferences",base());await expect(callTool("render_client_adapter",{workspace:join(workspace,"..","missing")})).rejects.toThrow();
  mkdirSync(join(workspace,".codex"));symlinkSync(root,join(workspace,".codex","agents"));await expect(callTool("render_client_adapter",{workspace})).rejects.toThrow("symlink");
  rmSync(join(workspace,".codex","agents"));const preview:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});writeFileSync(preview.files[0].path,readFileSync(preview.files[0].path,"utf8")+"changed");const ask:any=await callTool("uninstall_client_adapter",{});await expect(callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken})).rejects.toThrow("changed");
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
  await callTool("save_preferences",base());for(const fault of ["install-target-1","install-target-2","install-target-3","install-target-4","install-manifest-commit"]){const preview:any=await callTool("render_client_adapter",{workspace});__setManifestWriteFaultForTests(point=>{if(point===fault)throw new Error(`injected ${fault}`)});await expect(callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken})).rejects.toThrow(fault);expect(preview.files.every((f:any)=>!existsSync(f.path))).toBe(true);expect(existsSync(join(data,"managed-files.json"))).toBe(false);expect(existsSync(join(data,"transaction.json"))).toBe(false);}
  __setManifestWriteFaultForTests(undefined);
 });
 test("uninstall faults quarantine transaction and restore all files",async()=>{
  await callTool("save_preferences",base());const preview:any=await callTool("render_client_adapter",{workspace});await callTool("install_client_adapter",{workspace,confirmationToken:preview.confirmationToken});for(const fault of ["uninstall-target-1","uninstall-target-2","uninstall-target-3","uninstall-target-4","uninstall-manifest-commit"]){const ask:any=await callTool("uninstall_client_adapter",{});__setManifestWriteFaultForTests(point=>{if(point===fault)throw new Error(`injected ${fault}`)});await expect(callTool("uninstall_client_adapter",{confirmationToken:ask.confirmationToken})).rejects.toThrow(fault);for(const f of preview.files)expect(readFileSync(f.path,"utf8")).toBe(f.content);expect(JSON.parse(readFileSync(join(data,"managed-files.json"),"utf8")).files).toHaveLength(4);expect(existsSync(join(data,"transaction.json"))).toBe(false);}
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
