#!/usr/bin/env python3
"""
Playwright test with console capture to see actual JS errors.
"""
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright

async def test_with_real_server():
    """Test with a real server running in background."""
    
    # Start server in background
    env = os.environ.copy()
    env["PATH"] = "/home/lptop/Documents/coding/CleanSheet/.venv/bin:" + env.get("PATH", "")
    streamlit_proc = subprocess.Popen(
        ["/home/lptop/Documents/coding/CleanSheet/.venv/bin/streamlit", "run", "app.py", 
         "--server.headless", "true", "--server.port", "8528"],
        cwd="/home/lptop/Documents/coding/CleanSheet",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    await asyncio.sleep(10)
    
    if streamlit_proc.poll() is not None:
        stdout, stderr = streamlit_proc.communicate()
        print(f"Streamlit process exited: {streamlit_proc.returncode}")
        print(f"STDERR: {stderr.decode()[:2000]}")
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Capture console messages
        page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        
        try:
            await page.goto("http://localhost:8528", wait_until="networkidle", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(20)
            
            page_content = await page.content()
            
            checks = {
                "compare_two_groups": "Compare two groups" in page_content,
                "what_would_you_like": "What would you like to know" in page_content,
            }
            
            print("\nChecks:")
            for check, result in checks.items():
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"  {check}: {result}")
            
            await page.screenshot(path="/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/real_server_test.png")
            
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
    result = await test_with_real_server()
    print(f"\nResult: {result}")

if __name__ == "__main__":
    asyncio.run(main())