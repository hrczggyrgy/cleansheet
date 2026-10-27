#!/usr/bin/env python3
"""
Playwright test with proper selectbox interaction.
"""
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright

async def test_full_workflow():
    """Test the complete workflow with proper selectbox handling."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        env = os.environ.copy()
        env["PATH"] = "/home/lptop/Documents/coding/CleanSheet/.venv/bin:" + env.get("PATH", "")
        streamlit_proc = subprocess.Popen(
            ["/home/lptop/Documents/coding/CleanSheet/.venv/bin/streamlit", "run", "app.py", 
             "--server.headless", "true", "--server.port", "8514"],
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
            await page.goto("http://localhost:8514", wait_until="networkidle", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(15)
            
            # Step 1: Find and interact with the selectbox for demo datasets
            print("=== STEP 1: Select demo dataset ===")
            
            # Find the selectbox for demo datasets
            selectboxes = await page.locator('[data-testid="stSelectbox"]').all()
            print(f"Found {len(selectboxes)} selectboxes")
            
            if len(selectboxes) >= 1:
                # Click the first selectbox (dataset selector)
                await selectboxes[0].click()
                await asyncio.sleep(1)
                
                # Look for penguins option in dropdown
                penguins_option = page.locator("text=Palmer Penguins").first
                if await penguins_option.count() > 0:
                    await penguins_option.click()
                    print("✅ Selected 'Palmer Penguins'")
                    await asyncio.sleep(1)
                else:
                    print("❌ 'Palmer Penguins' not found in dropdown")
            
            # Step 2: Click Load Example
            print("\n=== STEP 2: Click Load Example ===")
            load_example = page.locator("button:has-text('Load Example')").first
            if await load_example.count() > 0:
                await load_example.click()
                print("✅ Clicked 'Load Example'")
                await asyncio.sleep(5)
            else:
                print("❌ 'Load Example' button not found")
            
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step1_loaded.png")
            
            # Step 2: Continue with this file
            print("\n=== STEP 2: Continue with this file ===")
            await asyncio.sleep(3)
            page_content = await page.content()
            
            continue_file = page.locator("button:has-text('Continue with this file')").first
            if await continue_file.count() > 0:
                print("✅ Found 'Continue with this file'")
                await continue_file.click()
                await asyncio.sleep(5)
            else:
                print("❌ 'Continue with this file' NOT found")
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
                
                # Select independent observations
                independent_btn = page.locator("button:has-text('Independent observations')").first
                if await independent_btn.count() > 0:
                    await independent_btn.click()
                    print("✅ Selected 'Independent observations'")
                    await asyncio.sleep(1)
                
                # Click Confirm & Continue
                confirm_btn = page.locator("button:has-text('Confirm')").first
                if await confirm_btn.count() > 0:
                    await confirm_btn.click()
                    print("✅ Clicked 'Confirm'")
                    await asyncio.sleep(3)
            else:
                print("❌ Study context NOT found")
                if "Study Context" in page_content:
                    print("Found 'Study Context' text")
                if "Study Design" in page_content:
                    print("Found 'Study Design' text")
            
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step3_study_context.png")
            
            # Step 4: Import review
            print("\n=== STEP 4: Import Review ===")
            await asyncio.sleep(3)
            page_content = await page.content()
            if "Confirm Import" in page_content:
                print("✅ Import review screen found")
                
                # Click Confirm Import & Continue
                confirm_import = page.locator("button:has-text('Confirm Import')").first
                if await confirm_import.count() > 0:
                    await confirm_import.click()
                    print("✅ Clicked 'Confirm Import & Continue'")
                    await asyncio.sleep(3)
            else:
                print("❌ Import review NOT found")
            
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step4_import_review.png")
            
            # Step 5: Preparation
            print("\n=== STEP 5: Preparation ===")
            await asyncio.sleep(5)
            page_content = await page.content()
            if "Continue to Question" in page_content:
                print("✅ Preparation screen found")
                continue_q = page.locator("button:has-text('Continue to Question')").first
                if await continue_q.count() > 0:
                    await continue_q.click()
                    print("✅ Clicked 'Continue to Question'")
                    await asyncio.sleep(3)
            else:
                print("❌ Preparation screen NOT found")
            
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/step5_preparation.png")
            
            # Step 6: Check for question cards
            print("\n=== STEP 6: Question Cards ===")
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
            
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/final_question_cards.png")
            
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