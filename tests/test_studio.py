"""Offline checks: never connect accounts or submit a real post."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import parse_qs,urlparse

import social
import social_accounts
import studio_plans


class LocalStudio(unittest.TestCase):
    def setUp(self):
        self.words=[{"text":text,"start":i,"end":i+.8} for i,text in enumerate(
            ["The","first","scene.","Um","costs","25!","They","tried","again.","Then","it","worked."])]
    def test_filler_preserves_surrounding_audio(self):
        cuts=studio_plans.dialogue_plan(self.words,0,12,"filler","")
        self.assertEqual(cuts,[{"start":0,"end":3},{"start":3.8,"end":12}])
    def test_beats_are_bounded(self):
        cuts=studio_plans.dialogue_plan(self.words,0,12,"beats","")
        self.assertTrue(any(c.get("cue") and c["zoom"]>1 for c in cuts))
        self.assertAlmostEqual(sum(c["end"]-c["start"] for c in cuts),12)
    def test_ai_effects_only_reference_selected_passages(self):
        with patch.object(studio_plans.smart,"_model",return_value="local"),patch.object(studio_plans.llm,"complete",return_value='{"indices":[0],"broll_indices":[0],"zoom_indices":[0]}'):
            rows=studio_plans.dialogue_plan(self.words,0,12,"edit","zoom","stock")
        self.assertEqual(rows[0]["broll"],"stock")
        self.assertEqual(rows[0]["zoom"],1.14)
    def test_model_cannot_select_unknown_passage(self):
        with patch.object(studio_plans.smart,"_model",return_value="local"),patch.object(studio_plans.llm,"complete",return_value='{"indices":[99]}'):
            with self.assertRaises(ValueError):studio_plans.dialogue_plan(self.words,0,12,"recap","")
    def test_no_resolution_in_trailer_candidate_pool(self):
        with patch.object(studio_plans.smart,"_model",return_value="local"),patch.object(studio_plans.llm,"complete",return_value='{"indices":[0]}') as model:
            studio_plans.dialogue_plan(self.words,0,12,"trailer","")
        self.assertNotIn('worked.',model.call_args.args[1]['prompt'])


class NativePosting(unittest.TestCase):
    def test_queue_window_observes_daily_cap_and_spacing(self):
        self.assertEqual(120, social.pick_post_slot(60,[60],1,0,0))
        self.assertEqual(86400, social.pick_post_slot(120,[60],0,1,0))
        self.assertEqual(86400-19800, social.pick_post_slot(120,[60],0,1,330))
    def test_oauth_callback_bound_to_original_request_and_one_use(self):
        with patch.dict("os.environ",{"NEONCLIPPING_YOUTUBE_CLIENT_ID":"test-id","NEONCLIPPING_YOUTUBE_TOKEN":""}),patch.object(social_accounts,"vault") as vault,patch.object(social_accounts,"exchange",return_value={"access_token":"fixture"}) as exchange:
            url=social_accounts.begin("youtube")["url"]
            params=parse_qs(urlparse(url).query)
            self.assertIn("code_challenge",params)
            callback=params["redirect_uri"][0]+"?code=fixture&state="+params["state"][0]
            self.assertEqual(social_accounts.finish(callback)["platform"],"youtube")
            self.assertTrue(exchange.call_args.args[1]["code_verifier"])
            self.assertEqual(vault.call_args.args[1]["access_token"],"fixture")
            with self.assertRaises(ValueError):social_accounts.finish(callback)

    def test_changed_account_aborts_before_upload(self):
        with patch.object(social,"account",return_value={"id":"changed","privacy":["private"]}),patch.object(social,"call") as api:
            with self.assertRaises(ValueError):social.publish({"account":"old","platform":"youtube","privacy":"private"},Path("."))
            api.assert_not_called()

    def test_direct_upload_adapters_use_local_file_or_explicit_instagram_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);(data/"clip.mp4").write_bytes(b"test media")
            for platform in social.PLATFORMS:
                row={"clip":"clip","platform":platform,"account":"owner","privacy":"private","title":"test","media_url":"https://example.org/clip.mp4"}
                def reply(method,url,provider=None,**kwargs):
                    result=Mock()
                    result.headers={}
                    if "googleapis.com/upload" in url:result.headers={"Location":"https://www.googleapis.com/session"}
                    elif url.endswith("/session"):result.json.return_value={"id":"yt"}
                    elif "api.x.com/2/media/upload/initialize" in url:result.json.return_value={"data":{"id":"xmedia"}}
                    elif "api.x.com/2/media/upload/xmedia/finalize" in url:result.json.return_value={"data":{"processing_info":{"state":"succeeded"}}}
                    elif url.endswith("/2/tweets"):result.json.return_value={"data":{"id":"xpost"}}
                    elif url.endswith("/media"):result.json.return_value={"id":"container"}
                    elif url.endswith("/container"):result.json.return_value={"status_code":"FINISHED"}
                    elif url.endswith("/media_publish"):result.json.return_value={"id":"ig"}
                    elif "graph.facebook.com" in url and "/me/accounts" in url:result.json.return_value={"data":[]}
                    elif "graph-video.facebook.com" in url:
                        phase=(kwargs.get("data") or {}).get("upload_phase")
                        if phase=="start":result.json.return_value={"upload_session_id":"fbsess","start_offset":"0","end_offset":"10"}
                        elif phase=="transfer":result.json.return_value={"start_offset":"10","end_offset":"10"}
                        else:result.json.return_value={"id":"fb"}
                    elif "video/init" in url:result.json.return_value={"error":{"code":"ok"},"data":{"publish_id":"tt","upload_url":"https://open-upload.tiktokapis.com/upload"}}
                    elif "action=initializeUpload" in url:result.json.return_value={"value":{"video":"urn:li:video:1","uploadInstructions":[{"uploadUrl":"https://dms-uploads.licdn.com/up","firstByte":0,"lastByte":9}]}}
                    elif "dms-uploads.licdn.com" in url:result.headers={"ETag":"etag1"}
                    elif url.endswith("/rest/posts"):result.headers={"x-restli-id":"li"}
                    elif url.endswith("/threads"):result.json.return_value={"id":"thc"}
                    elif url.endswith("/thc"):result.json.return_value={"status":"FINISHED"}
                    elif url.endswith("/threads_publish"):result.json.return_value={"id":"th"}
                    elif "custom.example.org" in url:result.json.return_value={"id":"cu"}
                    return result
                with self.subTest(platform=platform),patch.dict("os.environ",{"NEONCLIPPING_CUSTOM_UPLOAD_URL":"https://custom.example.org/hook"}),patch.object(social,"account",return_value={"id":"owner","privacy":["private"]}),patch.object(social,"call",side_effect=reply):
                    expected={"youtube":"yt","x":"xpost","instagram":"ig","facebook":"fb","tiktok":"tt","linkedin":"li","threads":"th","custom":"cu"}
                    self.assertEqual(social.publish(row,data),expected[platform])
    def test_duration_bias_needs_measured_comparable_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            with social.connect(data) as db:
                db.execute("CREATE TABLE posts(payload TEXT,metrics TEXT)")
                for i in range(6):
                    key=str(i)
                    (data/(key+".json")).write_text(json.dumps({"result":{"meta":{"duration":12 if i<3 else 42}}}))
                    db.execute("INSERT INTO posts VALUES(?,?)",(json.dumps({"clip":key,"platform":"youtube","account":"one"}),json.dumps({"views":1000,"likes":50 if i<3 else 10})))
            bias=social.duration_preferences(data)
            self.assertGreater(bias[0],0)
            self.assertLess(bias[2],0)
    def test_scheduling_deduplicates_and_cancels_in_same_queue(self):
        import time
        import uuid
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import jobs
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            data=Path(tmp);clip="b"*32
            (data/(clip+".mp4")).write_bytes(b"mock")
            (data/(clip+".json")).write_text('{"result":{"status":"done"}}')
            app=FastAPI();state={};handler=social.attach(app,data,state,lambda p:{"duration":5})
            jobs.attach(app,data,state,{"social":handler})
            try:
                with TestClient(app) as client,patch.object(social,"account",return_value={"id":"owner","name":"Creator","privacy":["private"]}),patch.object(social,"publish") as post:
                    body={"platform":"youtube","account":"owner","privacy":"private","title":"QA","clip":clip,"when":time.time()+3600,"request_id":str(uuid.uuid4())}
                    for _ in range(2):self.assertEqual(client.post("/social/posts",json=body).status_code,200)
                    result=client.get("/social/posts").json();self.assertEqual(len(result),1);self.assertEqual(result[0]["status"],"queued")
                    self.assertEqual(len(client.get("/queue").json()["jobs"]),1)
                    client.post("/queue/"+result[0]["job"]+"/cancel",json={}).raise_for_status()
                    self.assertEqual(client.get("/social/posts").json()[0]["status"],"canceled")
                    test_draft={**body,"request_id":str(uuid.uuid4()),"draft":True,"gap_minutes":10,"daily_cap":3}
                    saved=client.post("/social/posts",json=test_draft)
                    self.assertEqual(saved.status_code,200)
                    post_id=saved.json()["post"]
                    self.assertEqual(client.get("/social/posts").json()[0]["status"],"draft")
                    self.assertEqual(len(client.get("/queue").json()["jobs"]),1)
                    self.assertEqual(client.post(f"/social/posts/{post_id}/approve",json={}).status_code,200)
                    self.assertEqual(client.get("/social/posts").json()[0]["status"],"queued")
                    self.assertEqual(client.post(f"/social/posts/{post_id}/approve",json={}).status_code,409)
                    post.assert_not_called()
                    post.assert_not_called()
            finally:app.processing_queue.close()


class MultiPlatformAndAutoUpload(unittest.TestCase):
    def test_oauth_providers_x_facebook_linkedin_threads(self):
        for platform, expect_pkce in (("x", True), ("facebook", False), ("linkedin", False), ("threads", False)):
            env_prefix = "NEONCLIPPING_" + platform.upper() + "_"
            with self.subTest(platform=platform), patch.dict(
                "os.environ",
                {env_prefix + "CLIENT_ID": "cid", env_prefix + "CLIENT_SECRET": "csec", env_prefix + "TOKEN": ""},
            ), patch.object(social_accounts, "vault") as vault, patch.object(
                social_accounts, "exchange", return_value={"access_token": "tok"}
            ) as exchange:
                url = social_accounts.begin(platform)["url"]
                params = parse_qs(urlparse(url).query)
                if expect_pkce:
                    self.assertIn("code_challenge", params)
                else:
                    self.assertNotIn("code_challenge", params)
                callback = params["redirect_uri"][0] + "?code=code1&state=" + params["state"][0]
                self.assertEqual(social_accounts.finish(callback)["platform"], platform)
                self.assertTrue(exchange.called)
                self.assertEqual(vault.call_args.args[1]["access_token"], "tok")

    def test_account_and_metrics_for_new_platforms(self):
        def fake_call(method, url, platform=None, **kwargs):
            res = Mock()
            if url.endswith("/users/me"):
                res.json.return_value = {"data": {"id": "x1", "username": "creator"}}
            elif "/tweets/" in url:
                res.json.return_value = {"data": {"public_metrics": {"impression_count": 500, "like_count": 20, "reply_count": 3, "retweet_count": 7}}}
            elif "/me/accounts" in url:
                res.json.return_value = {"data": [{"id": "fb1", "name": "My Page", "access_token": "ptok"}]}
            elif "graph.facebook.com" in url and "/fbvid" in url:
                res.json.return_value = {"views": 900, "likes": {"summary": {"total_count": 40}}, "comments": {"summary": {"total_count": 5}}}
            elif url.endswith("/v2/userinfo"):
                res.json.return_value = {"sub": "li1", "name": "Ada"}
            elif "graph.threads.net" in url and url.endswith("/me"):
                res.json.return_value = {"id": "th1", "username": "ada_th"}
            elif "/insights" in url:
                res.json.return_value = {"data": [{"name": "views", "values": [{"value": 120}]}, {"name": "replies", "values": [{"value": 4}]}]}
            return res

        with patch.object(social, "call", side_effect=fake_call), patch.dict(
            "os.environ", {"NEONCLIPPING_CUSTOM_UPLOAD_URL": "https://hooks.example.org/up"}
        ):
            self.assertEqual(social.account("x")["name"], "@creator")
            self.assertEqual(social.account("facebook")["name"], "My Page")
            self.assertEqual(social.account("linkedin")["id"], "li1")
            self.assertEqual(social.account("threads")["name"], "ada_th")
            self.assertEqual(social.account("custom")["id"], "hooks.example.org")
            self.assertEqual(social.metrics("x", "tw1"), {"views": 500, "likes": 20, "comments": 3, "shares": 7})
            self.assertEqual(social.metrics("facebook", "fbvid"), {"views": 900, "likes": 40, "comments": 5})
            self.assertEqual(social.metrics("threads", "thpost"), {"views": 120, "comments": 4})

    def test_auto_upload_settings_validation_and_token_redaction(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import jobs

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            data = Path(tmp)
            app = FastAPI()
            social_accounts.attach(app)
            handler = social.attach(app, data, {}, lambda p: {"duration": 5})
            jobs.attach(app, data, {}, {"social": handler})
            try:
                with TestClient(app, base_url="http://127.0.0.1:8770") as client:
                    self.assertEqual(client.get("/social/platforms").status_code, 200)
                    self.assertEqual(client.post("/social/auto", json={"enabled": True, "platforms": []}).status_code, 400)
                    self.assertEqual(client.post("/social/auto", json={"custom_url": "http://evil.example.com/hook"}).status_code, 400)
                    self.assertEqual(client.post("/social/auto", json={"media_base_url": "http://127.0.0.1/clips"}).status_code, 400)
                    saved = client.post(
                        "/social/auto",
                        json={
                            "enabled": True,
                            "platforms": ["youtube", "x", "facebook", "custom"],
                            "min_score": 60,
                            "gap_minutes": 15,
                            "daily_cap": 3,
                            "custom_url": "https://upload.example.org/hook",
                            "custom_token": "secret-tok",
                        },
                    )
                    self.assertEqual(saved.status_code, 200)
                    body = saved.json()
                    self.assertTrue(body["enabled"])
                    self.assertTrue(body["has_custom_token"])
                    self.assertNotIn("custom_token", body)
                    fetched = client.get("/social/auto").json()
                    self.assertNotIn("custom_token", fetched)
                    self.assertTrue(fetched["has_custom_token"])
            finally:
                app.processing_queue.close()

    def test_auto_queue_clip_and_batch_publish(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import jobs

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            data = Path(tmp)
            clip_ok = "a" * 32
            clip_low = "c" * 32
            clip_flag = "d" * 32
            for cid in (clip_ok, clip_low, clip_flag):
                (data / (cid + ".mp4")).write_bytes(b"mock")
                (data / (cid + ".json")).write_text('{"result":{"status":"done"}}')

            app = FastAPI()
            state = {}
            handler = social.attach(app, data, state, lambda p: {"duration": 10})
            jobs.attach(app, data, state, {"social": handler})
            app.processing_queue.pause(True)
            try:
                social.save_auto_upload(
                    data,
                    {
                        "enabled": True,
                        "platforms": ["youtube", "x", "instagram", "facebook", "custom"],
                        "sources": ["make"],
                        "min_score": 70,
                        "skip_flagged": True,
                        "gap_minutes": 10,
                        "daily_cap": 5,
                        "media_base_url": "https://cdn.example.org/clips/{clip}.mp4",
                        "custom_url": "https://hooks.example.org/up",
                    },
                )

                def mock_account(p):
                    if p == "instagram":
                        return {"id": "ig1", "name": "IG", "privacy": ["account visibility"]}
                    if p == "x":
                        return {"id": "x1", "name": "@x", "privacy": ["everyone"]}
                    return {"id": p + "1", "name": p, "privacy": ["public"]}

                with patch.object(social, "account", side_effect=mock_account):
                    # Below min_score -> skipped completely
                    self.assertEqual(social.auto_queue_clip(app, data, {"file": clip_low, "title": "Low", "score": 40}, source="make"), [])

                    # Above min_score -> queued across all 5 platforms and deduplicated
                    res = social.auto_queue_clip(
                        app,
                        data,
                        {"file": clip_ok, "title": "Big win", "hashtags": ["gaming", "clutch"], "score": 85, "flags": []},
                        source="make",
                    )
                    self.assertEqual(len(res), 5)
                    self.assertTrue(all(r["status"] == "queued" for r in res))
                    dup = social.auto_queue_clip(app, data, {"file": clip_ok, "title": "Big win", "hashtags": ["gaming", "clutch"], "score": 85}, source="make")
                    self.assertTrue(all(r.get("duplicate") for r in dup))

                    # Flagged words -> saved as draft instead of queued
                    flagged_res = social.auto_queue_clip(
                        app,
                        data,
                        {"file": clip_flag, "title": "Flagged clip", "score": 90, "flags": ["badword"]},
                        source="make",
                    )
                    self.assertTrue(all(r["status"] == "draft" for r in flagged_res))

                    with TestClient(app) as client:
                        posts = client.get("/social/posts").json()
                        self.assertEqual(len(posts), 10)
                        batch = client.post(
                            "/social/posts/batch",
                            json={
                                "platforms": ["youtube", "x", "facebook"],
                                "clip": clip_low,
                                "title": "Manual multi-post",
                                "draft": True,
                            },
                        )
                        self.assertEqual(batch.status_code, 200)
                        self.assertEqual(len([r for r in batch.json()["results"] if r["ok"]]), 3)
            finally:
                app.processing_queue.close()

    def test_start_make_and_resume_interrupted_batch(self):
        import os
        import subprocess
        import time
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            old_dir = os.environ.get("NEONCLIPPING_DATA_DIR")
            os.environ["NEONCLIPPING_DATA_DIR"] = tmp
            try:
                import importlib
                import app as A
                importlib.reload(A)
                src_id = "f" * 32
                src_path = Path(tmp) / (src_id + ".mp4")
                subprocess.run(
                    [
                        "ffmpeg", "-nostdin", "-y", "-v", "error",
                        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12",
                        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6",
                        "-c:v", "libx264", "-c:a", "aac", str(src_path),
                    ],
                    check=True,
                )
                orig_export = A.start_export
                calls = []

                def fail_once(body, job=None, auto_source="export"):
                    calls.append(job)
                    if len(calls) == 1:
                        A.state[job] = {"status": "error", "error": "interrupted test"}
                        return {"job": job}
                    return orig_export(body, job, auto_source=auto_source)

                import transcripts
                words = [{"text": "hello", "start": i + 0.05, "end": i + 0.35} for i in range(6)]
                with TestClient(A.app) as client, patch.object(transcripts, "cached_source", return_value=words):
                    with patch.object(A, "start_export", side_effect=fail_once):
                        started = client.post(
                            "/make",
                            json={"id": src_id, "cam_auto": False, "resolution": 720, "moments": [{"start": 0, "end": 2}]},
                        )
                        self.assertEqual(started.status_code, 200)
                        orig_job = started.json()["job"]
                        deadline = time.monotonic() + 30
                        while time.monotonic() < deadline:
                            st = client.get(f"/make/{orig_job}").json()
                            if st["status"] != "running":
                                break
                            time.sleep(0.1)
                        self.assertEqual(st["status"], "error", st)
                        self.assertNotIn("local variable", st.get("error", ""))
                        self.assertTrue(st["can_resume"])
                        self.assertEqual(client.get("/make/resumable").json()["job"], orig_job)

                    resumed = client.post(f"/make/{orig_job}/resume")
                    self.assertEqual(resumed.status_code, 200)
                    res_job = resumed.json()["job"]
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        fin = client.get(f"/make/{res_job}").json()
                        if fin["status"] != "running":
                            break
                        time.sleep(0.1)
                    self.assertEqual(fin["status"], "done", fin)
                    self.assertFalse(client.get(f"/make/{orig_job}").json()["can_resume"])
                    self.assertIsNone(client.get("/make/resumable").json()["job"])
            finally:
                if old_dir is None:
                    os.environ.pop("NEONCLIPPING_DATA_DIR", None)
                else:
                    os.environ["NEONCLIPPING_DATA_DIR"] = old_dir

    def test_internal_export_hidden_from_runtime_and_make_status_and_reports_progress(self):
        import importlib
        import os
        import subprocess
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            old_dir = os.environ.get("NEONCLIPPING_DATA_DIR")
            os.environ["NEONCLIPPING_DATA_DIR"] = tmp
            try:
                import app as A
                A = importlib.reload(A)
                src_id = "abcdef1234567890abcdef1234567890"
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-v", "error",
                        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:d=3",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                        str(Path(tmp) / f"{src_id}.mp4"),
                    ],
                    check=True,
                )
                child_id = "11112222333344445555666677778888"
                A.state["parentmakejob00000000000000000001"] = {
                    "status": "running",
                    "stage": "Exporting clip 1/1",
                    "phase": "render",
                }
                A.state[child_id] = {
                    "status": "running",
                    "kind": "export",
                    "internal": True,
                    "parent_job": "parentmakejob00000000000000000001",
                    "message": "Rendering vertical clip with karaoke captions",
                    "progress": 0.42,
                }
                with TestClient(A.app) as client:
                    rt = client.get("/runtime").json()["active"]
                    ids = [x["id"] for x in rt]
                    self.assertIn("parentmakejob00000000000000000001", ids)
                    self.assertNotIn(child_id, ids)
                    self.assertEqual(client.get(f"/make/{child_id}").status_code, 404)
                    self.assertEqual(client.get(f"/status/{child_id}").status_code, 200)

                seen_progress = []
                out_mp4 = Path(tmp) / "prog_out.mp4"
                rc, err = A._run_ffmpeg_export(
                    [
                        "ffmpeg", "-y", "-v", "error", "-ss", "0", "-t", "2",
                        "-i", str(Path(tmp) / f"{src_id}.mp4"),
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(out_mp4),
                    ],
                    tmp,
                    2.0,
                    on_progress=seen_progress.append,
                )
                self.assertEqual(rc, 0, err)
                self.assertTrue(out_mp4.is_file())
                self.assertTrue(any(0 < p < 1.0 for p in seen_progress) or 1.0 in seen_progress, seen_progress)
                self.assertEqual(seen_progress[-1], 1.0)
            finally:
                if old_dir is None:
                    os.environ.pop("NEONCLIPPING_DATA_DIR", None)
                else:
                    os.environ["NEONCLIPPING_DATA_DIR"] = old_dir

    def test_resume_deduplicates_running_same_source_and_hides_stale_resumable(self):
        import importlib
        import os
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            old_dir = os.environ.get("NEONCLIPPING_DATA_DIR")
            os.environ["NEONCLIPPING_DATA_DIR"] = tmp
            try:
                import app as A
                A = importlib.reload(A)
                j1 = "aaaa1111222233334444555566667777"
                j2 = "bbbb1111222233334444555566667777"
                j_run = "cccc1111222233334444555566667777"
                for jid, si in ((j1, "one"), (j2, "two")):
                    (Path(tmp) / f"{jid}.resume.json").write_text(
                        json.dumps({"request": {"url": f"https://youtu.be/jwttobgA1w0?si={si}"}}),
                        encoding="utf-8",
                    )
                    A.state[jid] = {"id": jid, "status": "error", "error": "failed", "source": {"url": f"https://youtu.be/jwttobgA1w0?si={si}"}}
                A.state[j_run] = {
                    "id": j_run,
                    "status": "running",
                    "stage": "Preparing clip 1/6",
                    "phase": "prepare",
                    "source": {"url": "https://youtu.be/jwttobgA1w0"},
                    "title": "Running Video",
                }
                with TestClient(A.app) as client:
                    resumable = client.get("/make/resumable").json()
                    self.assertIsNone(resumable["job"])
                    self.assertEqual(resumable["active_job"], j_run)
                    resumed = client.post(f"/make/{j2}/resume").json()
                    self.assertEqual(resumed["job"], j_run)
            finally:
                if old_dir is None:
                    os.environ.pop("NEONCLIPPING_DATA_DIR", None)
                else:
                    os.environ["NEONCLIPPING_DATA_DIR"] = old_dir
