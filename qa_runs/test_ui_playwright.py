#!/usr/bin/env python3
"""
Playwright test to verify CleanSheet UI works with built-in demo data.
"""
import asyncio
import os
from playwright.async_api import async_playwright

async def test_cleansheet_ui():
    """Test the CleanSheet UI workflow with demo data."""
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Start the Streamlit app
        print("Starting Streamlit app...")
        
        # We need to start the app in background
        import subprocess
        import time
        
        # Start streamlit in background
        env = os.environ.copy()
        env["PATH"] = "/home/lptop/Documents/coding/CleanSheet/.venv/bin:" + env.get("PATH", "")
        streamlit_proc = subprocess.Popen(
            ["/home/lptop/Documents/coding/CleanSheet/.venv/bin/streamlit", "run", "app.py", 
             "--server.headless", "true", "--server.port", "8501"],
            cwd="/home/lptop/Documents/coding/CleanSheet",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for app to start
        await asyncio.sleep(10)
        
        try:
            # Navigate to the app
            print("Navigating to http://localhost:8501...")
            await page.goto("http://localhost:8501", wait_until="networkidle", timeout=30000)
            
            # Wait for page to load
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
            
            # Take screenshot of initial page
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/01_initial_page.png")
            print("Screenshot saved: 01_initial_page.png")
            
            # Check for demo data selector
            print("Looking for demo data options...")
            
            # Try to find and click "Load Example" or similar
            # The app has a "Load Example" button for built-in datasets
            load_example_btn = page.locator("button:has-text('Load Example')").first
            if await load_example_btn.count() > 0:
                print("Found 'Load Example' button")
                await load_example_btn.click()
                await asyncio.sleep(2)
                await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/02_after_load_example.png")
                print("Screenshot saved: 02_after_load_example.png")
            else:
                print("No 'Load Example' button found, checking for file uploader...")
                # Check for file uploader
                file_uploader = page.locator("input[type='file']").first
                if await file_uploader.count() > 0:
                    print("File uploader found")
                    # We can't easily upload a file in headless mode without a real file
                    # But we can check the page content
            
            # Check page content
            page_content = await page.content()
            
            # Look for key UI elements
            checks = {
                "title": "CleanSheet" in page_content or "No-code statistical analysis" in page_content,
                "upload": "Upload" in page_content or "Browse files" in page_content,
                "example": "Example" in page_content or "Demo" in page_content,
                "study_context": "Study Context" in page_content or "Study Design" in page_content,
            }
            
            print("\nUI Element Checks:")
            for check, result in checks.items():
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"  {check}: {status}")
            
            # Take final screenshot
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/03_final_state.png")
            print("\nScreenshot saved: 03_final_state.png")
            
            return checks
            
        except Exception as e:
            print(f"Error during test: {e}")
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/error_state.png")
            return {"error": str(e)}
        finally:
            streamlit_proc.terminate()
            await browser.close()

async def main():
    print("=" * 60)
    print("CleanSheet UI Playwright Test")
    print("=" * 60)
    
    os.makedirs("/home/lptop/Documents/coding/CleanSheet/qa_runs/screens", exist_ok=True)
    
    result = await test_cleansheet_ui()
    
    print("\n" + "=" * 60)
    print("Test Summary:")
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        passed = sum(1 for v in result.values() if v)
        total = len(result)
        print(f"  Passed: {passed}/{total}")
        for k, v in result.items():
            print(f"  {k}: {'✅' if v else '❌'}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())