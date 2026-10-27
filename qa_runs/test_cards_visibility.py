#!/usr/bin/env python3
"""
Playwright test to check the "Compare two groups" card visibility.
"""
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright

async def test_cleansheet_ui():
    """Test the CleanSheet UI workflow with demo data."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        env = os.environ.copy()
        env["PATH"] = "/home/lptop/Documents/coding/CleanSheet/.venv/bin:" + env.get("PATH", "")
        streamlit_proc = subprocess.Popen(
            ["/home/lptop/Documents/coding/CleanSheet/.venv/bin/streamlit", "run", "app.py", 
             "--server.headless", "true", "--server.port", "8511"],
            cwd="/home/lptop/Documents/coding/CleanSheet",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        await asyncio.sleep(15)
        
        if streamlit_proc.poll() is not None:
            stdout, stderr = streamlit_proc.communicate()
            print(f"Streamlit process exited: {streamlit_proc.returncode}")
            await browser.close()
            return
        
        try:
            await page.goto("http://localhost:8511", wait_until="networkidle", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(15)
            
            # Take screenshot
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/check_cards.png")
            
            # Check for the question cards
            page_content = await page.content()
            
            checks = {
                "compare_two_groups_label": "Compare two groups" in page_content,
                "compare_two_groups_desc": "Compare a numeric outcome between two groups" in page_content,
                "compare_3_groups": "Compare 3+ groups" in page_content,
                "compare_before_after": "Compare before/after" in page_content,
                "explore_linear": "Explore linear relationship" in page_content,
                "explore_monotonic": "Explore monotonic relationship" in page_content,
                "test_category": "Test category association" in page_content,
                "describe_data": "Describe my data" in page_content,
                "select_button": "Select" in page_content,
                "what_would_you_like": "What would you like to know" in page_content,
            }
            
            print("\nCard Visibility Checks:")
            for check, result in checks.items():
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"  {check}: {status}")
            
            # Check for buttons
            buttons = await page.locator("button").all()
            print(f"\nTotal buttons: {len(buttons)}")
            for btn in buttons:
                text = await btn.text_content()
                if text and text.strip():
                    print(f"  Button: '{text.strip()}'")
            
            # Check for the specific card container
            card_containers = await page.locator('[data-testid="stVerticalBlock"]').all()
            print(f"\nVertical blocks: {len(card_containers)}")
            
            return checks
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
        finally:
            streamlit_proc.terminate()
            try:
                streamlit_proc.wait(timeout=5)
            except:
                streamlit_proc.kill()
            await browser.close()

async def main():
    os.makedirs("/home/lptop/Documents/coding/CleanSheet/qa_runs/screens", exist_ok=True)
    result = await test_cleansheet_ui()
    
    if "error" not in result:
        passed = sum(1 for v in result.values() if v)
        total = len(result)
        print(f"\nPassed: {passed}/{total}")

if __name__ == "__main__":
    asyncio.run(main())