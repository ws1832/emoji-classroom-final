"""Real Vue navigation labels with isolated HTTP fixtures, no users or camera."""

import asyncio
import os

from playwright.async_api import async_playwright, expect


async def main():
    web_url = os.environ.get("WEB_NAV_TEST_URL", "http://localhost:3100").rstrip("/")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()

            async def api(route):
                path = route.request.url.split("/api/v1", 1)[1].split("?", 1)[0]
                data = []
                if path == "/base/userinfo":
                    data = {
                        "id": 1,
                        "username": "fixture-teacher",
                        "is_active": True,
                        "role_codes": ["TEACHER"],
                        "roles": [],
                        "is_superuser": False,
                    }
                await route.fulfill(
                    json={"code": 200, "msg": "OK", "data": data, "total": 0, "page": 1, "page_size": 20}
                )

            await context.route("**/api/v1/**", api)
            await context.add_init_script("""(() => {
                localStorage.setItem('LOCALE', JSON.stringify({value:'cn',expire:null}));
                localStorage.setItem('ACCESS_TOKEN', JSON.stringify({value:'fixture-only',expire:null}));
                localStorage.setItem('TAGS', JSON.stringify({value:[
                    {path:'/teacher/classroom',name:'TeacherClassroomHome',title:'TeacherClassroomHome'}
                ],expire:null}));
            })()""")
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(web_url + "/teacher/classroom")
            await expect(page.get_by_text("我的课程与课堂", exact=True)).to_be_visible()
            await expect(page.locator(".side-menu")).to_contain_text("我的课堂")
            await expect(page.locator("body")).not_to_contain_text("TeacherClassroomHome")
            await expect(page.locator(".n-breadcrumb-item")).to_have_count(1)
            assert (await page.title()).startswith("我的课堂 | ")
            tags = await page.evaluate("JSON.parse(localStorage.getItem('TAGS')).value")
            assert len(tags) == 1 and tags[0]["title"] == "我的课堂"
            assert not errors, errors
            print("Chromium: Chinese menu/title/tab; legacy cached label refreshed without duplicate tabs.")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
