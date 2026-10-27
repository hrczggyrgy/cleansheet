#!/usr/bin/env python3
"""
Playwright test to verify CleanSheet UI works with built-in demo data - interactive version.
"""
import asyncio
import os
import subprocess
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
        
        env = os.environ.copy()
        env["PATH"] = "/home/lptop/Documents/coding/CleanSheet/.venv/bin:" + env.get("PATH", "")
        streamlit_proc = subprocess.Popen(
            ["/home/lptop/Documents/coding/CleanSheet/.venv/bin/streamlit", "run", "app.py", 
             "--server.headless", "true", "--server.port", "8510"],
            cwd="/home/lptop/Documents/coding/CleanSheet",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for app to start
        print("Waiting for Streamlit to start...")
        await asyncio.sleep(15)
        
        if streamlit_proc.poll() is not None:
            stdout, stderr = streamlit_proc.communicate()
            print(f"Streamlit process exited with code {streamlit_proc.returncode}")
            await browser.close()
            return {"error": "Streamlit process died"}
        
        try:
            # Navigate to the app
            print("Navigating to http://localhost:8510...")
            await page.goto("http://localhost:8510", wait_until="networkidle", timeout=60000)
            
            # Wait for page to load
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(15)  # Wait for React app to fully load
            
            # Take screenshot of initial page
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/01_initial_page.png")
            print("Screenshot saved: 01_initial_page.png")
            
            # Try to interact with the app using Streamlit's test selectors
            print("Looking for file uploader...")
            
            # Streamlit file uploader has a specific structure
            file_uploader = page.locator('[data-testid="stFileUploader"]').first
            if await file_uploader.count() > 0:
                print("✅ Found file uploader via data-testid")
            else:
                print("❌ File uploader not found via data-testid")
            
            # Look for buttons with specific test IDs
            buttons = await page.locator('[data-testid="stButton"]').all()
            print(f"Found {len(buttons)} stButton elements")
            
            # Look for selectboxes
            selects = await page.locator('[data-testid="stSelectbox"]').all()
            print(f"Found {len(selects)} stSelectbox elements")
            
            # Look for radio buttons
            radios = await page.locator('[data-testid="stRadio"]').all()
            print(f"Found {len(radios)} stRadio elements")
            
            # Look for file uploader dropzone
            dropzone = page.locator('[data-testid="stFileUploaderDropzone"]').first
            if await dropzone.count() > 0:
                print("✅ Found file uploader dropzone")
            
            # Check for the main app content
            page_content = await page.content()
            
            # Check for CleanSheet specific content
            checks = {
                "cleansheet_title": "CleanSheet" in page_content,
                "streamlit_app": "streamlit" in page_content.lower(),
            }
            
            # Try to find text content
            if "Add data" in page_content:
                checks["step_1"] = True
                print("✅ Found 'Add data' step")
            else:
                checks["step_1"] = False
                print("❌ 'Add data' step not found")
            
            if "Study context" in page_content:
                checks["step_2"] = True
                print("✅ Found 'Study context' step")
            else:
                checks["step_2"] = False
                print("❌ 'Study context' step not found")
            
            if "Prepare data" in page_content:
                checks["step_3"] = True
                print("✅ Found 'Prepare data' step")
            else:
                checks["step_3"] = False
                print("❌ 'Prepare data' step not found")
            
            if "Ask a question" in page_content:
                checks["step_4"] = True
                print("✅ Found 'Ask a question' step")
            else:
                checks["step_4"] = False
                print("❌ 'Ask a question' step not found")
            
            # Check for sidebar elements
            if "Progress" in page_content:
                checks["sidebar_progress"] = True
                print("✅ Found sidebar progress")
            else:
                checks["sidebar_progress"] = False
                print("❌ Sidebar progress not found")
            
            if "Start over" in page_content:
                checks["start_over"] = True
                print("✅ Found 'Start over' button")
            else:
                checks["start_over"] = False
                print("❌ 'Start over' button not found")
            
            # Check for demo data options
            if "penguins" in page_content.lower() or "iris" in page_content.lower() or "tips" in page_content.lower():
                checks["demo_data"] = True
                print("✅ Found demo data references")
            else:
                checks["demo_data"] = False
                print("❌ Demo data references not found")
            
            # Take final screenshot
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/03_final_state.png")
            print("\nScreenshot saved: 03_final_state.png")
            
            return checks
            
        except Exception as e:
            print(f"Error during test: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/error_state.png")
            return {"error": str(e)}
        finally:
            streamlit_proc.terminate()
            try:
                streamlit_proc.wait(timeout=5)
            except:
                streamlit_proc.kill()
            await browser.close()

async def main():
    print("=" * 60)
    print("CleanSheet UI Playwright Test (Interactive)")
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