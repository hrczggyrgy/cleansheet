#!/usr/bin/env python3
"""
Playwright test with detailed debugging at each stage.
"""
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright

async def test_full_workflow():
    """Test the complete workflow to reach question cards with detailed debugging."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        env = os.environ.copy()
        env["PATH"] = "/home/lptop/Documents/coding/CleanSheet/.venv/bin:" + env.get("PATH", "")
        streamlit_proc = subprocess.Popen(
            ["/home/lptop/Documents/coding/CleanSheet/.venv/bin/streamlit", "run", "app.py", 
             "--server.headless", "true", "--server.port", "8513"],
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
            await page.goto("http://localhost:8513", wait_until="networkidle", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(15)
            
            # Take screenshot of initial state
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step0_start.png")
            
            # Step 1: Check initial page content
            page_content = await page.content()
            print("=== INITIAL PAGE ===")
            print(f"Content length: {len(page_content)}")
            
            # Check for Load Example
            load_example = page.locator("button:has-text('Load Example')").first
            if await load_example.count() > 0:
                print("✅ Found 'Load Example' button")
                await load_example.click()
                await asyncio.sleep(2)
                await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step1_load_example.png")
                
                # Check for penguins option
                page_content = await page.content()
                print(f"After Load Example click, content length: {len(page_content)}")
                
                # Look for penguins in dropdown or list
                penguins_options = await page.locator("text=penguins").all()
                print(f"Found {len(penguins_options)} 'penguins' text elements")
                
                # Try to find and click penguins in a selectbox or list
                selectboxes = await page.locator('[data-testid="stSelectbox"]').all()
                print(f"Found {len(selectboxes)} selectboxes")
                
                for i, sb in enumerate(selectboxes):
                    try:
                        await sb.click()
                        await asyncio.sleep(1)
                        # Look for penguins in dropdown
                        penguins_in_dropdown = page.locator("text=penguins").first
                        if await penguins_in_dropdown.count() > 0:
                            await penguins_in_dropdown.click()
                            print("✅ Selected penguins in dropdown")
                            break
                    except:
                        pass
                await asyncio.sleep(2)
            
            # Step 2: Continue with this file
            page_content = await page.content()
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step1_after_penguins.png")
            
            print("\n=== STEP 2: Continue with this file ===")
            continue_file = page.locator("button:has-text('Continue with this file')").first
            if await continue_file.count() > 0:
                print("✅ Found 'Continue with this file'")
                await continue_file.click()
                await asyncio.sleep(5)
            else:
                print("❌ 'Continue with this file' NOT found")
                # Check what buttons are available
                buttons = await page.locator("button").all()
                for btn in buttons:
                    text = await btn.text_content()
                    if text and text.strip():
                        print(f"  Button: '{text.strip()}'")
            
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step2_after_continue.png")
            
            # Step 3: Study context
            print("\n=== STEP 3: Study Context ===")
            await asyncio.sleep(5)
            page_content = await page.content()
            print(f"Content length: {len(page_content)}")
            
            if "Row structure" in page_content or "How were observations collected" in page_content:
                print("✅ Study context screen found")
                await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step3_study_context.png")
            else:
                print("❌ Study context NOT found")
                # Check for other indicators
                if "Study Context" in page_content:
                    print("Found 'Study Context' text")
                if "Study Design" in page_content:
                    print("Found 'Study Design' text")
            
            # Step 4: Import review
            print("\n=== STEP 4: Import Review ===")
            await asyncio.sleep(3)
            page_content = await page.content()
            if "Confirm Import" in page_content:
                print("✅ Import review screen found")
            else:
                print("❌ Import review NOT found")
            
            # Final check
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/final_state.png")
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
            
            print("\nFinal Question Card Checks:")
            for check, result in checks.items():
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"  {check}: {status}")
            
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