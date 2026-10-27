#!/usr/bin/env python3
"""
Playwright test to verify the complete workflow to reach question cards.
"""
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright

async def test_full_workflow():
    """Test the complete workflow to reach question cards."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        env = os.environ.copy()
        env["PATH"] = "/home/lptop/Documents/coding/CleanSheet/.venv/bin:" + env.get("PATH", "")
        streamlit_proc = subprocess.Popen(
            ["/home/lptop/Documents/coding/CleanSheet/.venv/bin/streamlit", "run", "app.py", 
             "--server.headless", "true", "--server.port", "8512"],
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
            await page.goto("http://localhost:8512", wait_until="networkidle", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(15)
            
            # Step 1: Load example data (penguins)
            print("Step 1: Looking for 'Load Example' button...")
            load_example = page.locator("button:has-text('Load Example')").first
            if await load_example.count() > 0:
                await load_example.click()
                await asyncio.sleep(2)
                
                # Select penguins
                print("Selecting penguins dataset...")
                penguins_option = page.locator("button:has-text('penguins')").first
                if await penguins_option.count() > 0:
                    await penguins_option.click()
                    await asyncio.sleep(3)
            
            # Step 2: Continue with this file
            print("Step 2: Looking for 'Continue with this file'...")
            continue_file = page.locator("button:has-text('Continue with this file')").first
            if await continue_file.count() > 0:
                await continue_file.click()
                await asyncio.sleep(3)
            
            # Step 3: Study context - should show next
            print("Step 3: Checking for study context...")
            await asyncio.sleep(3)
            
            # Look for study context options
            page_content = await page.content()
            if "Row structure" in page_content or "How were observations collected" in page_content:
                print("Study context screen found")
                
                # Select independent observations
                independent_btn = page.locator("button:has-text('Independent observations')").first
                if await independent_btn.count() > 0:
                    await independent_btn.click()
                    await asyncio.sleep(1)
                
                # Click Confirm & Continue
                confirm_btn = page.locator("button:has-text('Confirm')").first
                if await confirm_btn.count() > 0:
                    await confirm_btn.click()
                    await asyncio.sleep(3)
            
            # Step 4: Import review - Confirm Import & Continue
            print("Step 4: Import review...")
            await asyncio.sleep(3)
            page_content = await page.content()
            if "Confirm Import" in page_content:
                confirm_import = page.locator("button:has-text('Confirm Import')").first
                if await confirm_import.count() > 0:
                    await confirm_import.click()
                    await asyncio.sleep(3)
            
            # Step 5: Preparation - Continue to Question
            print("Step 5: Preparation screen...")
            await asyncio.sleep(3)
            page_content = await page.content()
            if "Continue to Question" in page_content:
                continue_q = page.locator("button:has-text('Continue to Question')").first
                if await continue_q.count() > 0:
                    await continue_q.click()
                    await asyncio.sleep(3)
            
            # Step 6: Check for question cards
            print("Step 6: Checking for question cards...")
            await asyncio.sleep(3)
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
                "what_would_you_like": "What would you like to know" in page_content,
            }
            
            print("\nQuestion Card Checks:")
            for check, result in checks.items():
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"  {check}: {status}")
            
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/full_workflow.png")
            
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
    result = await test_full_workflow()
    
    if "error" not in result:
        passed = sum(1 for v in result.values() if v)
        total = len(result)
        print(f"\nPassed: {passed}/{total}")

if __name__ == "__main__":
    asyncio.run(main())