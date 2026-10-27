#!/usr/bin/env python3
"""
Inspect the actual HTML structure of the start page.
"""
import asyncio
import os
import subprocess
from playwright.async_api import async_playwright

async def inspect_html():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        env = os.environ.copy()
        env["PATH"] = "/home/lptop/Documents/coding/CleanSheet/.venv/bin:" + env.get("PATH", "")
        streamlit_proc = subprocess.Popen(
            ["/home/lptop/Documents/coding/CleanSheet/.venv/bin/streamlit", "run", "app.py", 
             "--server.headless", "true", "--server.port", "8515"],
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
            await page.goto("http://localhost:8515", wait_until="networkidle", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(15)
            
            # Get full page HTML
            page_content = await page.content()
            
            # Save full HTML for inspection
            with open("/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/page_html.html", "w") as f:
                f.write(page_content)
            
            print("=== FULL PAGE HTML SAVED ===")
            
            # Look for selectbox-related elements
            print("\n=== Looking for selectbox elements ===")
            import re
            selectbox_matches = re.findall(r'<[^>]*select[^>]*>', page_content, re.IGNORECASE)
            print(f"Found {len(selectbox_matches)} select-like elements")
            for m in selectbox_matches[:10]:
                print(f"  {m[:200]}")
            
            # Look for Load Example button
            load_example_matches = re.findall(r'<[^>]*Load Example[^>]*>', page_content, re.IGNORECASE)
            print(f"\nFound {len(load_example_matches)} 'Load Example' button elements")
            for m in load_example_matches[:5]:
                print(f"  {m[:200]}")
            
            # Look for Choose a dataset
            dataset_matches = re.findall(r'<[^>]*Choose a dataset[^>]*>', page_content, re.IGNORECASE)
            print(f"\nFound {len(dataset_matches)} 'Choose a dataset' elements")
            for m in dataset_matches[:5]:
                print(f"  {m[:200]}")
            
            # Look for data-testid attributes
            testid_matches = re.findall(r'data-testid="[^"]*"', page_content)
            print(f"\nFound {len(testid_matches)} data-testid attributes")
            for m in testid_matches[:20]:
                print(f"  {m}")
            
            # Save a truncated version for easier reading
            with open("/home/lptop/Documents/coding/CleanSheet/qa_runs/screens/page_truncated.html", "w") as f:
                # Save first 50000 chars
                f.write(page_content[:50000])
            
            return {"saved": True}
            
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
    result = await inspect_html()
    print(f"\nResult: {result}")

if __name__ == "__main__":
    asyncio.run(main())