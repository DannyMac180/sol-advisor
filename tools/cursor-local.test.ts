import { afterEach, describe, expect, test } from "bun:test";
import { chmodSync, existsSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { mkdtempSync } from "node:fs";
import { installCursorLocal, uninstallCursorLocal } from "./cursor-local";

const roots: string[] = [];
afterEach(() => { for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true }); });

function fixture(existingMcp?: object) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "sol-advisor-cursor-local-test-")));
  roots.push(root);
  const source = join(root, "source");
  const workspace = join(root, "workspace");
  const cursorRoot = join(root, "cursor");
  const bunPath = join(root, "bin", "bun");
  mkdirSync(join(source, "mcp"), { recursive: true });
  mkdirSync(join(source, "skills", "setup"), { recursive: true });
  mkdirSync(workspace);
  mkdirSync(join(root, "bin"));
  writeFileSync(join(source, "plugin.json"), '{"$schema":"test","name":"sol-advisor"}\n');
  writeFileSync(join(source, "mcp.json"), '{"$schema":"test","mcpServers":{"sol-advisor":{"type":"stdio","command":"bun"}}}\n');
  writeFileSync(join(source, "mcp", "server.ts"), "console.log('server');\n");
  writeFileSync(join(source, "skills", "setup", "SKILL.md"), "---\nname: setup\n---\n");
  writeFileSync(bunPath, "#!/bin/sh\nexit 0\n");
  chmodSync(bunPath, 0o755);
  if (existingMcp) {
    mkdirSync(join(workspace, ".cursor"));
    writeFileSync(join(workspace, ".cursor", "mcp.json"), `${JSON.stringify(existingMcp, null, 2)}\n`);
  }
  return { root, source, workspace, cursorRoot, bunPath, platform: "darwin" as const };
}
const readJson = (path: string) => JSON.parse(readFileSync(path, "utf8"));

describe("Cursor local compatibility installer", () => {
  test("installs a physical plugin copy and project-native MCP overlay", () => {
    const f = fixture();
    const result = installCursorLocal(f);
    expect(existsSync(join(result.target, "plugin.json"))).toBe(true);
    expect(readJson(join(result.target, "mcp.json")).mcpServers).toEqual({});
    const config = readJson(result.workspaceMcp);
    expect(config.mcpServers["sol-advisor"]).toEqual({
      command: f.bunPath,
      args: [join(result.target, "mcp", "server.ts")],
      cwd: result.target,
      env: { PLUGIN_DATA: result.data },
    });
    expect(existsSync(join(result.target, ".sol-advisor-cursor-local.json"))).toBe(true);
  });

  test("preserves unrelated project MCP entries through install and uninstall", () => {
    const existing = { mcpServers: { other: { command: "other" } }, note: "preserve" };
    const f = fixture(existing);
    installCursorLocal(f);
    expect(readJson(join(f.workspace, ".cursor", "mcp.json")).mcpServers.other).toEqual({ command: "other" });
    uninstallCursorLocal(f);
    expect(readJson(join(f.workspace, ".cursor", "mcp.json"))).toEqual(existing);
    expect(existsSync(join(f.cursorRoot, "plugins", "local", "sol-advisor"))).toBe(false);
  });

  test("removes its MCP file while preserving workspace-local plugin data", () => {
    const f = fixture();
    const installed = installCursorLocal(f);
    uninstallCursorLocal(f);
    expect(existsSync(installed.workspaceMcp)).toBe(false);
    expect(existsSync(installed.data)).toBe(true);
    expect(installed.data.startsWith(join(f.workspace, ".cursor"))).toBe(true);
  });

  test("refuses symlinked Cursor path components", () => {
    const f = fixture();
    const external = join(f.root, "external-cursor");
    mkdirSync(external);
    symlinkSync(external, f.cursorRoot);
    expect(() => installCursorLocal(f)).toThrow("Cursor root has a symlink component");
    expect(existsSync(join(external, "plugins", "local", "sol-advisor"))).toBe(false);
  });

  test("refuses an existing server name without mutating it", () => {
    const existing = { mcpServers: { "sol-advisor": { command: "unmanaged" } } };
    const f = fixture(existing);
    expect(() => installCursorLocal(f)).toThrow("already defines sol-advisor");
    expect(readJson(join(f.workspace, ".cursor", "mcp.json"))).toEqual(existing);
    expect(existsSync(join(f.cursorRoot, "plugins", "local", "sol-advisor"))).toBe(false);
  });

  test("refuses to uninstall a changed plugin or changed project entry", () => {
    const first = fixture();
    const installed = installCursorLocal(first);
    writeFileSync(join(installed.target, "tampered.txt"), "changed\n");
    expect(() => uninstallCursorLocal(first)).toThrow("changed local plugin");

    const second = fixture();
    const installedSecond = installCursorLocal(second);
    const config = readJson(installedSecond.workspaceMcp);
    config.mcpServers["sol-advisor"].command = "tampered";
    writeFileSync(installedSecond.workspaceMcp, `${JSON.stringify(config, null, 2)}\n`);
    expect(() => uninstallCursorLocal(second)).toThrow("changed sol-advisor entry");
  });

  test("validates receipt authority against the freshly expected project entry", () => {
    const f = fixture();
    const installed = installCursorLocal(f);
    const receiptPath = join(installed.target, ".sol-advisor-cursor-local.json");
    const receipt = readJson(receiptPath);
    receipt.projectEntry.command = "/tmp/attacker";
    writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
    expect(() => uninstallCursorLocal(f)).toThrow("receipt is invalid");
    expect(existsSync(installed.target)).toBe(true);
  });

  test("recovers an interrupted install with a managed copy but missing MCP entry", () => {
    const f = fixture();
    const installed = installCursorLocal(f);
    rmSync(installed.workspaceMcp);
    const recovered = installCursorLocal(f);
    expect(recovered.recovered).toBe(true);
    expect(readJson(recovered.workspaceMcp).mcpServers["sol-advisor"]).toBeDefined();
  });

  test("recovers an interrupted uninstall from its deterministic quarantine", () => {
    const f = fixture();
    const installed = installCursorLocal(f);
    const quarantine = join(f.cursorRoot, "plugins", "local", ".sol-advisor.removing");
    renameSync(installed.target, quarantine);
    const result = uninstallCursorLocal(f);
    expect(result.recovered).toBe(true);
    expect(existsSync(quarantine)).toBe(false);
    expect(existsSync(installed.workspaceMcp)).toBe(false);
  });

  test("refuses concurrent MCP edits during install without losing the edit", () => {
    const existing = { mcpServers: { other: { command: "before" } } };
    const f = fixture(existing);
    const mcpPath = join(f.workspace, ".cursor", "mcp.json");
    expect(() => installCursorLocal({ ...f, beforeMcpCommit: () => {
      const changed = readJson(mcpPath);
      changed.mcpServers.other.command = "concurrent";
      writeFileSync(mcpPath, `${JSON.stringify(changed, null, 2)}\n`);
    } })).toThrow("changed concurrently");
    expect(readJson(mcpPath).mcpServers.other.command).toBe("concurrent");
    expect(existsSync(join(f.cursorRoot, "plugins", "local", "sol-advisor"))).toBe(false);
  });

  test("refuses concurrent MCP edits during uninstall and restores the plugin", () => {
    const f = fixture({ mcpServers: { other: { command: "before" } } });
    const installed = installCursorLocal(f);
    expect(() => uninstallCursorLocal({ ...f, beforeMcpCommit: () => {
      const changed = readJson(installed.workspaceMcp);
      changed.mcpServers.other.command = "concurrent";
      writeFileSync(installed.workspaceMcp, `${JSON.stringify(changed, null, 2)}\n`);
    } })).toThrow("changed concurrently");
    expect(readJson(installed.workspaceMcp).mcpServers.other.command).toBe("concurrent");
    expect(existsSync(installed.target)).toBe(true);
  });

  test("uninstall refuses a managed Cursor-root symlink swap", () => {
    const f = fixture();
    const installed = installCursorLocal(f);
    const movedRoot = join(f.root, "cursor-moved");
    renameSync(f.cursorRoot, movedRoot);
    symlinkSync(movedRoot, f.cursorRoot);
    expect(() => uninstallCursorLocal(f)).toThrow("Cursor root has a symlink component");
    expect(existsSync(join(movedRoot, "plugins", "local", "sol-advisor"))).toBe(true);
    expect(existsSync(installed.workspaceMcp)).toBe(true);
  });

  test("fails closed outside the live-tested macOS host", () => {
    const f = fixture();
    expect(() => installCursorLocal({ ...f, platform: "linux" })).toThrow("supports macOS only");
  });

});
