#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本机薄包装执行端点：把「这里能跑的全自动新建宝贝」变成一次 HTTP 调用。

为什么需要它：
  Obsidian / SKILL.md 只是说明书。外部 harness 只有 LLM + 文档读取能力，
  拿不到本机 Python、edge-bridge 登录态、sops 凭据、多阶段编排与留证。
  本服务把那些运行时留在这台机器上，只对外暴露一个受控入口。

安全边界（重要）：
  - 只监听 127.0.0.1，绝不绑 0.0.0.0。
  - 默认 dry=true：不建草稿、不发布、不生图、不写线上商品。
  - 线上写操作必须同时给 {"dry": false, "confirm": "GO"}，否则 400。
  - 全局串行锁：同一时刻只允许一个任务，避免并发写线上商品。
  - 可选 --token：启用后所有请求需带 X-Onepipe-Token。
  - 命令里不含任何凭据；sops/age 只通过环境变量注入。
  - 每个任务落 onepipe_jobs/<id>.json + .log，便于审计。

用法：
  python onepipe_service.py --host 127.0.0.1 --port 8788
  python onepipe_service.py --port 8788 --token <自选口令>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import preflight_env

HERE = Path(__file__).resolve().parent
JOBS_DIR = HERE / "onepipe_jobs"
AGE_KEY = preflight_env.AGE_KEY

RUN_LOCK = threading.Lock()
CURRENT_JOB = {"id": None}
AUTH_TOKEN = ""

# 只透传 create_from_pno.py 真实存在的参数，杜绝拼错或注入新选项
STR_OPTIONS = {
    "keyword": "--keyword",
    "title": "--title",
    "desc": "--desc",
    "additional": "--additional",
    "price": "--price",
    "outer_id": "--outer-id",
    "template_gid": "--template-gid",
    "ref": "--ref",
    "account_label": "--account-label",
    "recharge_types": "--recharge-types",
    "main_image_sku_mode": "--main-image-sku-mode",
    "title_sku_mode": "--title-sku-mode",
}
BOOL_OPTIONS = {
    "nopublish": "--nopublish",
    "noimg": "--noimg",
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _save(job_id: str, rec: dict):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    (JOBS_DIR / (job_id + ".json")).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_value(v) -> str:
    """值不能以 - 开头，避免被子进程 argparse 当成新选项。"""
    s = str(v)
    if s.startswith("-"):
        raise ValueError("参数值不能以 - 开头: %s" % s[:40])
    if "\x00" in s:
        raise ValueError("参数值含 NUL")
    return s


def _build_onepipe_argv(body: dict):
    pno = body.get("pno")
    if pno is None or str(pno).strip() == "":
        raise ValueError("缺少必填参数 pno")
    if not re.fullmatch(r"[0-9A-Za-z_-]{1,40}", str(pno)):
        raise ValueError("pno 只能是字母/数字/_/-，且不超过 40 字符")
    try:
        acct = int(body.get("acct", 95425))
    except (TypeError, ValueError):
        raise ValueError("acct 必须是整数（志远 95425 / 思券 99569）")

    dry = body.get("dry", True)
    if not isinstance(dry, bool):
        raise ValueError("dry 必须是 true/false")
    if not dry and body.get("confirm") != "GO":
        raise PermissionError("线上写操作必须显式给 confirm:'GO'；默认只跑 dry")

    argv = ["--acct", str(acct), "--pno", _safe_value(pno)]
    for key, flag in STR_OPTIONS.items():
        if key not in body or body[key] in (None, ""):
            continue
        val = _safe_value(body[key])
        if key == "main_image_sku_mode" and val not in ("highest", "all"):
            raise ValueError("main_image_sku_mode 只能是 highest 或 all")
        argv += [flag, val]
    for key, flag in BOOL_OPTIONS.items():
        if body.get(key) is True:
            argv.append(flag)
    argv.append("--dry" if dry else "--go")
    return argv, dry


def _run_job(script: str, argv: list, meta: dict, job_id: str | None = None,
             timeout: int = 900) -> dict:
    job_id = job_id or uuid.uuid4().hex[:12]
    cmd = [sys.executable, str(HERE / script)] + [str(a) for a in argv]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("SOPS_AGE_KEY_FILE", str(AGE_KEY))

    rec = {
        "job_id": job_id,
        "state": "running",
        "started_at": _now(),
        "script": script,
        "argv": argv,
        "command": cmd,
        "dry": meta.get("dry"),
        "caller": meta.get("caller", ""),
    }
    _save(job_id, rec)

    stdout, stderr, rc, error = "", "", None, None
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=str(HERE), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout)
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        error = "超时 %ss" % timeout
        stdout = exc.stdout or "" if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr or "" if isinstance(exc.stderr, str) else ""
    except Exception as exc:
        error = "%s: %s" % (type(exc).__name__, exc)
        stderr = traceback.format_exc()
    duration = round(time.time() - t0, 2)

    # dry 无损保护：create_from_pno.py --dry 会重写本地 spec_from_pno_<pno>.json
    # （既有行为，会把 goods 置空）。这里把 dry 预览另存到 jobs 目录，
    # 并把原有 spec 原样恢复，避免 harness 反复 dry 洗掉历史 spec。
    dry_spec = meta.get("dry_spec_path")
    if dry_spec:
        sp = Path(dry_spec)
        before = meta.get("dry_spec_before")
        try:
            if sp.is_file():
                after = sp.read_bytes()
                if after != before:
                    JOBS_DIR.mkdir(parents=True, exist_ok=True)
                    preview = JOBS_DIR / (job_id + "_spec_dry.json")
                    preview.write_bytes(after)
                    rec["spec_preview"] = str(preview)
                    if before is not None:
                        sp.write_bytes(before)
                        rec["spec_restored"] = "原有 spec 已原样恢复；dry 预览另存"
                    else:
                        sp.unlink(missing_ok=True)
                        rec["spec_restored"] = "dry 新建的 spec 已移走；原位置保持不存在"
            else:
                rec["spec_restored"] = "dry 未生成 spec 文件，无需恢复"
        except Exception as exc:
            rec["spec_restore_error"] = "%s: %s" % (type(exc).__name__, exc)

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    (JOBS_DIR / (job_id + ".log")).write_text(
        "# command: %s\n# cwd: %s\n# started: %s\n\n=== STDOUT ===\n%s\n\n=== STDERR ===\n%s\n"
        % (" ".join(cmd), HERE, rec["started_at"], stdout, stderr), encoding="utf-8")

    rec.update({
        "state": "done" if error is None else "failed",
        "finished_at": _now(),
        "duration_s": duration,
        "exit_code": rc,
        "ok": error is None and rc == 0,
        "error": error,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-2000:],
        "log_file": str(JOBS_DIR / (job_id + ".log")),
    })
    _save(job_id, rec)
    return rec


def _locked_run(script, argv, meta, job_id=None, timeout=900):
    """串行执行；忙时立即返回 409，不排队，避免并发写线上商品。"""
    if not RUN_LOCK.acquire(blocking=False):
        return None, 409
    try:
        CURRENT_JOB["id"] = job_id or "pending"
        return _run_job(script, argv, meta, job_id=job_id, timeout=timeout), 200
    finally:
        CURRENT_JOB["id"] = None
        RUN_LOCK.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "OnePipeBridge/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (_now(), fmt % args))

    def _send(self, obj, code=200):
        raw = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        if not AUTH_TOKEN:
            return True
        if self.headers.get("X-Onepipe-Token") == AUTH_TOKEN:
            return True
        return parse_qs(urlparse(self.path).query).get("token", [""])[0] == AUTH_TOKEN

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 1024 * 1024:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        if not raw.strip():
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    def _guard(self):
        if not self._authorized():
            self._send({"error": "unauthorized", "hint": "需要 X-Onepipe-Token 头"}, 401)
            return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path == "/":
            self._send({
                "service": "onepipe-bridge",
                "version": "1.0",
                "note": "本机运行时包装端点；默认只读 dry，线上写需显式 confirm",
                "endpoints": {
                    "GET /health": "轻量存活检查",
                    "GET /preflight": "只读环境自检（bridge/token/脚本/凭据/素材）",
                    "GET /jobs/<id>": "查询任务状态与结果",
                    "GET /show?gid=<ID>": "读主图复刻记录（白名单/核验状态）",
                    "POST /onepipe": "新建宝贝一条龙。body: {acct,pno,keyword?,template_gid?,dry?,confirm?}",
                    "POST /inspect": "商品巡检。body: {gid}",
                    "POST /verify-image": "主图逐字核验盖章。body: {gid,note}",
                },
                "defaults": {"dry": True, "async": False, "timeout_s": 900},
                "write_guard": "dry=false 且 confirm='GO' 才允许线上写操作",
                "docs": "HARNESS_ONEPIPE.md",
            })
            return
        if path == "/health":
            self._send({"ok": True, "service": "onepipe-bridge", "time": _now(),
                        "busy": bool(CURRENT_JOB["id"]), "running_job": CURRENT_JOB["id"],
                        "tools_dir": str(HERE)})
            return
        if path == "/preflight":
            result = preflight_env.run(with_token=True)
            self._send(result, 200 if result["ready"] else 503)
            return
        if path.startswith("/jobs/"):
            jid = path.split("/jobs/", 1)[1]
            if not jid or not jid.replace("-", "").isalnum():
                self._send({"error": "bad job id"}, 400)
                return
            f = JOBS_DIR / (jid + ".json")
            if not f.is_file():
                self._send({"error": "job not found", "job_id": jid}, 404)
                return
            self._send(json.loads(f.read_text(encoding="utf-8")))
            return
        if path == "/show":
            gid = qs.get("gid", [""])[0]
            if not gid.isdigit():
                self._send({"error": "gid 必须是数字"}, 400)
                return
            rec, code = _locked_run("replica_main_image.py", ["--show", "--gid", gid],
                                    {"dry": True}, timeout=60)
            self._send(rec or {"error": "busy", "running_job": CURRENT_JOB["id"]}, code)
            return
        self._send({"error": "not found", "path": path}, 404)

    def do_POST(self):
        if not self._guard():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            body = self._body()
        except Exception as exc:
            self._send({"error": "bad request", "detail": str(exc)}, 400)
            return

        if path == "/onepipe":
            try:
                argv, dry = _build_onepipe_argv(body)
            except PermissionError as exc:
                self._send({"error": "write_guard", "detail": str(exc)}, 400)
                return
            except Exception as exc:
                self._send({"error": "bad parameters", "detail": str(exc)}, 400)
                return

            pre = preflight_env.run(with_token=True)
            if not pre["ready"]:
                self._send({"error": "runtime not ready", "preflight": pre}, 503)
                return

            timeout = int(body.get("timeout_s", 900))
            timeout = max(60, min(timeout, 1800))
            spec_path = HERE / Path("spec_from_pno_%s.json" % str(body.get("pno"))).name
            spec_before = spec_path.read_bytes() if spec_path.is_file() else None
            meta = {
                "dry": dry,
                "caller": str(body.get("caller", ""))[:80],
                "dry_spec_path": str(spec_path) if dry else "",
                "dry_spec_before": spec_before,
            }
            async_mode = body.get("async") is True

            if async_mode:
                jid = uuid.uuid4().hex[:12]
                rec = {"job_id": jid, "state": "queued", "started_at": _now(),
                       "dry": dry, "script": "create_from_pno.py", "argv": argv}
                _save(jid, rec)

                def worker():
                    result, _ = _locked_run("create_from_pno.py", argv, meta,
                                           job_id=jid, timeout=timeout)
                    if result is None:
                        rec.update({"state": "failed", "error": "busy",
                                    "running_job": CURRENT_JOB["id"]})
                        _save(jid, rec)

                threading.Thread(target=worker, daemon=True).start()
                self._send({"accepted": True, "job_id": jid, "state": "queued",
                            "poll": "GET /jobs/%s" % jid, "dry": dry}, 202)
                return

            rec, code = _locked_run("create_from_pno.py", argv, meta, timeout=timeout)
            if rec is None:
                self._send({"error": "busy", "running_job": CURRENT_JOB["id"],
                            "hint": "已有任务在跑；串行锁防止并发写线上商品"}, 409)
                return
            rec["next"] = {
                "dry": "通过后把 dry 改 false 并加 confirm:'GO' 才会真正建宝贝",
                "go": "跑完调 POST /inspect {gid} 巡检；主图仍需 POST /verify-image 盖章",
            }
            self._send(rec, code if rec.get("ok") else 500)
            return

        if path == "/inspect":
            gid = str(body.get("gid", ""))
            if not gid.isdigit():
                self._send({"error": "gid 必须是数字"}, 400)
                return
            rec, code = _locked_run("onepipe_guard.py", ["--inspect", "--gid", gid],
                                    {"dry": True}, timeout=180)
            self._send(rec or {"error": "busy", "running_job": CURRENT_JOB["id"]},
                       code if rec else 409)
            return

        if path == "/verify-image":
            gid = str(body.get("gid", ""))
            note = str(body.get("note", "")).strip()
            if not gid.isdigit() or not note:
                self._send({"error": "需要 gid（数字）与 note（逐字核验结论）"}, 400)
                return
            note = note[:500].replace("\n", " ")
            if note.startswith("-"):
                note = " " + note
            rec, code = _locked_run(
                "replica_main_image.py",
                ["--mark-verified", "--gid", gid, "--note", note],
                {"dry": False, "caller": "verify-image"}, timeout=60)
            self._send(rec or {"error": "busy", "running_job": CURRENT_JOB["id"]},
                       code if rec else 409)
            return

        self._send({"error": "not found", "path": path}, 404)

    def do_HEAD(self):
        self._send({}, 405)


def main():
    global AUTH_TOKEN
    ap = argparse.ArgumentParser(description="一条龙运行时包装端点")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--token", default="", help="可选：启用后请求需带 X-Onepipe-Token")
    args = ap.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        ap.error("安全限制：只允许绑定本机回环地址")
    AUTH_TOKEN = args.token
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("onepipe-bridge listening on http://%s:%s" % (args.host, args.port))
    print("  GET  /            查看调用契约")
    print("  GET  /preflight   只读环境自检")
    print("  POST /onepipe     新建宝贝（默认 dry）")
    print("  docs: HARNESS_ONEPIPE.md")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
