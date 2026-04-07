#!/usr/bin/env python3
"""
方案 C: 本地 HTTP API 服务器 — 插件热管理

提供 RESTful API 管理 Claude Code 插件。修改 settings.json 后通过信号文件
通知正在运行的 Claude Code session（由 UserPromptSubmit hook 消费）。

启动: python3 plugin_server.py [--port 9800]

API:
  GET  /plugins                     列出所有插件及状态
  GET  /plugins/<name>              查看单个插件详情
  POST /plugins/enable              启用插件  {"plugins": ["mongodb", "stripe"]}
  POST /plugins/disable             禁用插件  {"plugins": ["mongodb"]}
  POST /plugins/scan                扫描项目并自动配置  {"project_dir": "/path/to/project"}
  POST /plugins/reload              写入重载信号通知 Claude Code
  POST /plugins/restore             恢复所有插件为启用
  GET  /status                      服务器状态
"""

import json
import sys
import os
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

SETTINGS_FILE = Path.home() / ".claude/settings.json"
SIGNAL_FILE = Path(tempfile.gettempdir()) / "claude-plugin-hotload-signal.json"
MARKETPLACE_SUFFIX = "@claude-plugins-official"
CLAUDE_DIR = Path(__file__).parent.parent
ROOT_DIR = CLAUDE_DIR.parent

# 导入 plugin_manager 的功能
sys.path.insert(0, str(CLAUDE_DIR))


def load_settings():
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_signal(action: str, details: str):
    """写入信号文件，供 hook 消费。"""
    signal = {
        "action": action,
        "details": details,
        "timestamp": datetime.now().isoformat(),
    }
    SIGNAL_FILE.write_text(json.dumps(signal, ensure_ascii=False))


def get_all_plugins():
    """获取所有插件及其状态。"""
    settings = load_settings()
    plugins = {}
    for key, enabled in settings.get("enabledPlugins", {}).items():
        name = key.replace(MARKETPLACE_SUFFIX, "")
        plugins[name] = {"enabled": enabled, "key": key}
    return plugins


def set_plugins_state(names: list, enabled: bool):
    """批量设置插件启用/禁用状态。"""
    settings = load_settings()
    changed = []
    not_found = []
    for name in names:
        key = f"{name}{MARKETPLACE_SUFFIX}"
        if key in settings.get("enabledPlugins", {}):
            if settings["enabledPlugins"][key] != enabled:
                settings["enabledPlugins"][key] = enabled
                changed.append(name)
        else:
            not_found.append(name)
    if changed:
        save_settings(settings)
    return changed, not_found


def scan_project(project_dir: str):
    """调用 plugin_manager 扫描项目。"""
    try:
        from plugin_manager import load_rules, determine_plugins, apply_plugins
        rules = load_rules()
        needed = determine_plugins(project_dir, rules)
        changes = apply_plugins(needed, dry_run=False)
        return {
            "needed": sorted(needed),
            "enabled": sorted(changes["enabled"]),
            "disabled": sorted(changes["disabled"]),
        }
    except Exception as e:
        return {"error": str(e)}


class PluginAPIHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器。"""

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        if path == "/status":
            self._send_json({
                "status": "running",
                "settings_file": str(SETTINGS_FILE),
                "signal_file": str(SIGNAL_FILE),
                "signal_pending": SIGNAL_FILE.exists(),
            })

        elif path == "/plugins":
            plugins = get_all_plugins()
            enabled = sum(1 for p in plugins.values() if p["enabled"])
            disabled = len(plugins) - enabled
            self._send_json({
                "total": len(plugins),
                "enabled": enabled,
                "disabled": disabled,
                "plugins": {
                    name: info["enabled"] for name, info in sorted(plugins.items())
                },
            })

        elif path.startswith("/plugins/"):
            name = path.split("/plugins/")[1]
            plugins = get_all_plugins()
            if name in plugins:
                # 附加 skill 信息
                info = plugins[name]
                cache_file = CLAUDE_DIR / "cache" / "skills_index.json"
                skills = []
                if cache_file.exists():
                    index = json.loads(cache_file.read_text())
                    plugin_data = index.get("plugins", {}).get(name, {})
                    skills = list(plugin_data.get("skills", {}).keys())
                self._send_json({
                    "name": name,
                    "enabled": info["enabled"],
                    "skills": skills,
                })
            else:
                self._send_json({"error": f"插件 '{name}' 不存在"}, 404)

        else:
            self._send_json({"error": "未知路径", "available": [
                "GET  /status",
                "GET  /plugins",
                "GET  /plugins/<name>",
                "POST /plugins/enable",
                "POST /plugins/disable",
                "POST /plugins/scan",
                "POST /plugins/reload",
                "POST /plugins/restore",
            ]}, 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")

        if path == "/plugins/enable":
            body = self._read_body()
            names = body.get("plugins", [])
            if not names:
                self._send_json({"error": "需要 plugins 数组"}, 400)
                return
            changed, not_found = set_plugins_state(names, True)
            if changed:
                write_signal(
                    "已启用插件",
                    f"启用了: {', '.join(changed)}"
                )
            self._send_json({
                "changed": changed,
                "not_found": not_found,
                "message": f"已启用 {len(changed)} 个插件" if changed else "无变更",
            })

        elif path == "/plugins/disable":
            body = self._read_body()
            names = body.get("plugins", [])
            if not names:
                self._send_json({"error": "需要 plugins 数组"}, 400)
                return
            changed, not_found = set_plugins_state(names, False)
            if changed:
                write_signal(
                    "已禁用插件",
                    f"禁用了: {', '.join(changed)}"
                )
            self._send_json({
                "changed": changed,
                "not_found": not_found,
                "message": f"已禁用 {len(changed)} 个插件" if changed else "无变更",
            })

        elif path == "/plugins/scan":
            body = self._read_body()
            project_dir = body.get("project_dir", "")
            if not project_dir or not os.path.isdir(project_dir):
                self._send_json({"error": f"无效目录: {project_dir}"}, 400)
                return
            result = scan_project(project_dir)
            if "error" not in result:
                if result["enabled"] or result["disabled"]:
                    write_signal(
                        "项目扫描完成",
                        f"启用: {result['enabled']}, 禁用: {result['disabled']}"
                    )
            self._send_json(result)

        elif path == "/plugins/reload":
            write_signal("手动重载请求", "用户通过 API 请求重载插件")
            self._send_json({
                "message": "重载信号已写入，下次用户发送消息时 Claude Code 将收到通知",
            })

        elif path == "/plugins/restore":
            settings = load_settings()
            count = 0
            for key in settings.get("enabledPlugins", {}):
                if not settings["enabledPlugins"][key]:
                    settings["enabledPlugins"][key] = True
                    count += 1
            if count:
                save_settings(settings)
                write_signal("恢复所有插件", f"已恢复 {count} 个插件为启用")
            self._send_json({"restored": count})

        else:
            self._send_json({"error": "未知路径"}, 404)

    def log_message(self, format, *args):
        """自定义日志格式。"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        sys.stderr.write(f"[{timestamp}] {args[0]}\n")


def main():
    port = 9800
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    server = HTTPServer(("127.0.0.1", port), PluginAPIHandler)
    print(f"插件管理 API 服务器已启动: http://127.0.0.1:{port}")
    print(f"设置文件: {SETTINGS_FILE}")
    print(f"信号文件: {SIGNAL_FILE}")
    print()
    print("API 端点:")
    print(f"  GET  http://127.0.0.1:{port}/status")
    print(f"  GET  http://127.0.0.1:{port}/plugins")
    print(f"  GET  http://127.0.0.1:{port}/plugins/<name>")
    print(f"  POST http://127.0.0.1:{port}/plugins/enable")
    print(f"  POST http://127.0.0.1:{port}/plugins/disable")
    print(f"  POST http://127.0.0.1:{port}/plugins/scan")
    print(f"  POST http://127.0.0.1:{port}/plugins/reload")
    print(f"  POST http://127.0.0.1:{port}/plugins/restore")
    print()
    print("Ctrl+C 停止服务器")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        server.server_close()


if __name__ == "__main__":
    main()
