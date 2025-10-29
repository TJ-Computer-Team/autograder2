#!/usr/bin/env python3
"""Simulate the interactive checker locally"""

import subprocess
import sys

def run_interactor(secret, query_or_answer):
    """Simulate running the interactor once"""
    interactor_input = f"{secret}\n{query_or_answer}\n"
    result = subprocess.run(
        ["./interactor_test"],
        input=interactor_input,
        capture_output=True,
        text=True,
        timeout=1.0
    )
    return result.stdout.strip(), result.returncode

def main():
    secret = 42
    
    # Start user solution
    user_proc = subprocess.Popen(
        ["python3", "test_solution.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    query_count = 0
    max_queries = 10
    
    try:
        while True:
            # Read line from user program
            line = user_proc.stdout.readline().strip()
            
            if not line:
                print("User program ended without output")
                break
            
            print(f"User: {line}")
            
            if line.startswith("?"):
                query_count += 1
                if query_count > max_queries:
                    print(f"ERROR: Exceeded {max_queries} queries")
                    break
                
                # Run interactor
                response, returncode = run_interactor(secret, line)
                print(f"Interactor: {response}")
                
                if returncode != 0:
                    print(f"ERROR: Interactor failed with return code {returncode}")
                    break
                
                # Send response back to user
                user_proc.stdin.write(response + "\n")
                user_proc.stdin.flush()
            
            elif line.startswith("!"):
                # Check final answer
                response, returncode = run_interactor(secret, line)
                print(f"Interactor: {response}")
                
                if "AC" in response:
                    print("✓ ACCEPTED")
                else:
                    print("✗ WRONG ANSWER")
                break
            
            else:
                print(f"ERROR: Invalid format: {line}")
                break
        
        user_proc.terminate()
        user_proc.wait(timeout=1)
        
    except Exception as e:
        print(f"ERROR: {e}")
        user_proc.kill()

if __name__ == "__main__":
    main()

