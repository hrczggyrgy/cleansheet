#!/usr/bin/env python3
"""
Playwright test to verify CleanSheet UI works with built-in demo data - updated version.
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
             "--server.headless", "true", "--server.port", "8509"],
            cwd="/home/lptop/Documents/coding/CleanSheet",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for app to start
        print("Waiting for Streamlit to start...")
        await asyncio.sleep(15)
        
        # Check if process is still running
        if streamlit_proc.poll() is not None:
            stdout, stderr = streamlit_proc.communicate()
            print(f"Streamlit process exited with code {streamlit_proc.returncode}")
            print(f"STDOUT: {stdout.decode()[:1000]}")
            print(f"STDERR: {stderr.decode()[:1000]}")
            await browser.close()
            return {"error": "Streamlit process died"}
        
        try:
            # Navigate to the app
            print("Navigating to http://localhost:8509...")
            response = await page.goto("http://localhost:8509", wait_until="networkidle", timeout=60000)
            print(f"Response status: {response.status if response else 'None'}")
            
            # Wait for page to load - Streamlit needs time to load React app
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(10)  # Wait for React app to load
            
            # Take screenshot of initial page
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/01_initial_page.png")
            print("Screenshot saved: 01_initial_page.png")
            
            # Get page content
            page_content = await page.content()
            print(f"Page content length: {len(page_content)}")
            
            # Check for key UI elements in the rendered React app
            checks = {
                "streamlit_loaded": "streamlit" in page_content.lower(),
                "has_root": "root" in page_content.lower() or "main" in page_content.lower(),
            }
            
            # Wait for the actual app content to render
            # Look for CleanSheet-specific content
            print("Waiting for CleanSheet app content...")
            
            # Try to find file uploader or other UI elements
            for attempt in range(10):
                await asyncio.sleep(2)
                page_content = await page.content()
                
                # Check for CleanSheet content
                if "CleanSheet" in page_content or "Upload" in page_content or "Load Example" in page_content:
                    print(f"Found CleanSheet content on attempt {attempt + 1}")
                    break
                elif "stFileUploader" in page_content or "stButton" in page_content:
                    print(f"Found Streamlit components on attempt {attempt + 1}")
                    break
            
            # Final content check
            page_content = await page.content()
            
            checks = {
                "cleansheet_title": "CleanSheet" in page_content,
                "upload": "Upload" in page_content or "upload" in page_content.lower(),
                "example": "Example" in page_content or "Demo" in page_content or "penguins" in page_content.lower(),
                "file_uploader": "stFileUploader" in page_content or 'type="file"' in page_content,
                "button": "Load Example" in page_content or "button" in page_content.lower(),
            }
            
            print("\nUI Element Checks:")
            for check, result in checks.items():
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"  {check}: {status}")
            
            # Try to find specific elements
            print("\nLooking for specific elements...")
            
            # Check for buttons
            buttons = await page.locator("button").all()
            print(f"Found {len(buttons)} buttons")
            for btn in buttons[:10]:
                text = await btn.text_content()
                if text and text.strip():
                    print(f"  Button: {text.strip()}")
            
            # Check for file upload
            file_inputs = await page.locator("input[type='file']").all()
            print(f"Found {len(file_inputs)} file inputs")
            
            # Check for select boxes
            selects = await page.locator("select").all()
            print(f"Found {len(selects)} select elements")
            
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
    print("CleanSheet UI Playwright Test (Updated)")
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