#!/usr/bin/env python3
# Binary search solution for number guessing game (1-1000)

def main():
    left = 1
    right = 1000
    
    for _ in range(10):  # Max 10 queries
        if left == right:
            break
        
        mid = (left + right) // 2
        print(f"? {mid}", flush=True)
        
        response = input().strip()
        
        if response == "=":
            print(f"! {mid}", flush=True)
            return
        elif response == "<":
            right = mid - 1
        else:  # response == ">"
            left = mid + 1
    
    # Final answer
    print(f"! {left}", flush=True)

if __name__ == "__main__":
    main()

