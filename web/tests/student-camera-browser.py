"""实际Vue采集控件：可选真实硬件；默认模拟MediaStream，不保存图片/trace。"""

import asyncio
import json
import os
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect


async def main():
    config = json.loads(os.environ["STUDENT_CAMERA_TEST_CONFIG"])
    hardware = config.get("hardware", False)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not hardware, args=["--use-fake-ui-for-media-stream"])
        errors = []
        context = await browser.new_context(permissions=["camera"])
        await context.add_init_script(
            """
            window.__cameraTracks=[];
            window.__captureCalls=0;
            const nativeGet=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
            navigator.mediaDevices.getUserMedia=async(options)=>{
                window.__captureCalls++;
                const stream=await nativeGet(options);
                window.__cameraTracks.push(...stream.getTracks());
                return stream;
            };
        """
        )
        if not hardware:
            await context.add_init_script(
                """
                navigator.mediaDevices.getUserMedia=async()=>{
                    window.__captureCalls++;
                    const canvas=document.createElement('canvas');
                    canvas.width=640;canvas.height=480;
                    const draw=()=>{canvas.getContext('2d').fillRect(0,0,640,480)};
                    draw();const timer=setInterval(draw,100);
                    const stream=canvas.captureStream(10);
                    const track=stream.getVideoTracks()[0];
                    const stop=track.stop.bind(track);
                    track.stop=()=>{clearInterval(timer);stop()};
                    window.__cameraTracks.push(track);
                    return stream;
                };
            """
            )
        page = await context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        statuses = []

        async def response(r):
            if "/ai-stream/frames" in r.url or ":9998/frames" in r.url:
                try:
                    statuses.append((r.status, (await r.json()).get("status")))
                except Exception:
                    pass

        page.on("response", response)
        try:
            await page.goto(config["web_url"] + "/login")
            await page.get_by_placeholder("用户名", exact=True).fill(config["username"])
            await page.get_by_placeholder("密码", exact=True).fill(config["password"])
            await page.locator('button[type="submit"]').click()
            await page.wait_for_url(lambda u: "/login" not in urlsplit(u).path)
            await page.goto(config["web_url"] + "/student/classroom")
            await page.locator(".n-select").first.click()
            await page.get_by_text(config["course_name"], exact=False).last.click()
            await expect(page.get_by_text("摄像头匿名反馈（可选）", exact=True)).to_be_visible()
            await expect(page.get_by_role("button", name="开启摄像头", exact=True)).to_be_enabled()
            await page.get_by_role("button", name="开启摄像头", exact=True).click()
            await expect(page.locator("video")).to_be_visible(timeout=20000)
            await expect(page.get_by_role("button", name="停止摄像头", exact=True)).to_be_enabled()
            await page.wait_for_function("document.querySelector('video')?.videoWidth>0")
            await page.wait_for_timeout(config.get("duration_ms", 24000))
            assert statuses, "No real HTTP frame was observed"
            assert any(code == 200 for code, _ in statuses), statuses
            storage = await page.evaluate("JSON.stringify(localStorage)+JSON.stringify(sessionStorage)")
            assert "bcc_" not in storage and "aic_" not in storage
            assert await page.evaluate("window.__captureCalls") == 1
            await page.get_by_role("button", name="停止摄像头", exact=True).click()
            await page.wait_for_function("window.__cameraTracks.every(t=>t.readyState==='ended')")
            await expect(page.locator("video")).not_to_be_visible()
            requests_before = len(statuses)
            await page.wait_for_timeout(1200)
            assert len(statuses) == requests_before
            assert not errors, errors
            print(
                json.dumps(
                    {
                        "mode": "hardware-getUserMedia" if hardware else "simulated-MediaStream",
                        "frame_responses": statuses,
                        "tracks_released": True,
                        "secret_storage": False,
                        "page_errors": errors,
                    },
                    ensure_ascii=True,
                )
            )
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
