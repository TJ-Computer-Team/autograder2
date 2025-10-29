import subprocess
import time
import threading
import os
from pathlib import Path
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class InteractiveRunner:
    
    def __init__(
        self,
        user_cmd: list,
        interactor_cmd: list,
        test_input_path: Optional[str],
        answer_path: Optional[str],
        queries_path: Optional[str],
        time_limit_ms: int,
        memory_limit_mb: int,
    ):
        self.user_cmd = user_cmd
        self.interactor_cmd = interactor_cmd
        self.test_input_path = test_input_path
        self.answer_path = answer_path
        self.time_limit_ms = time_limit_ms
        self.memory_limit_mb = memory_limit_mb
        
        self.max_queries = 10000 
        if queries_path and os.path.exists(queries_path):
            try:
                with open(queries_path, 'r') as f:
                    self.max_queries = int(f.read().strip())
            except Exception as e:
                logger.warning(f"Failed to read query limit from {queries_path}: {e}, using default")
        
        self.verdict = "Accepted"
        self.message = ""
        self.query_count = 0
        self.start_time = None
        self.error_occurred = False
        self.got_answer = False
        
    def run(self) -> Tuple[str, str, int]:
        self.start_time = time.time()
        
        try:
            user_process = subprocess.Popen(
                self.user_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            
            test_input_data = ""
            if self.test_input_path and os.path.exists(self.test_input_path):
                with open(self.test_input_path, 'r') as f:
                    test_input_data = f.read()
        
            answer_data = ""
            if self.answer_path and os.path.exists(self.answer_path):
                with open(self.answer_path, 'r') as f:
                    answer_data = f.read()
            
            if test_input_data:
                try:
                    user_process.stdin.write(test_input_data)
                    if not test_input_data.endswith('\n'):
                        user_process.stdin.write('\n')
                    user_process.stdin.flush()
                except Exception as e:
                    return "Grader Error", f"Failed to send initial input to user: {e}", 0
            
            interaction_thread = threading.Thread(
                target=self._interact,
                args=(user_process, test_input_data, answer_data),
                daemon=True
            )
            interaction_thread.start()
            
            timeout_seconds = self.time_limit_ms / 1000.0
            interaction_thread.join(timeout=timeout_seconds)
            
            elapsed_ms = int((time.time() - self.start_time) * 1000)
            
            if interaction_thread.is_alive():
                user_process.kill()
                return "Time Limit Exceeded", "", min(elapsed_ms, self.time_limit_ms)
            
            # Only report Runtime Error if return code is explicitly non-zero
            # returncode is None if process is still running (shouldn't happen after join)
            if user_process.returncode is not None and user_process.returncode != 0:
                stderr = user_process.stderr.read() if user_process.stderr else ""
                return "Runtime Error", stderr[:1000], elapsed_ms
            
            if not self.got_answer and self.verdict == "Accepted":
                return "Runtime Error", "Program exited without submitting answer", elapsed_ms
            
            return self.verdict, self.message, elapsed_ms
            
        except Exception as e:
            elapsed_ms = int((time.time() - self.start_time) * 1000)
            return "Grader Error", f"Exception: {str(e)}", elapsed_ms
    
    def _interact(self, user_process, test_input_data, answer_data):
        try:
            # Parse T (number of test cases) from the first line
            T = 1  # Default to single test case
            if test_input_data:
                lines = test_input_data.strip().split('\n')
                try:
                    T = int(lines[0])
                except (ValueError, IndexError):
                    T = 1  # If can't parse, assume 1
            
            # Track test case results
            current_test = 0
            test_cases_passed = 0
            
            while True:
                elapsed = (time.time() - self.start_time) * 1000
                if elapsed >= self.time_limit_ms:
                    self.verdict = "Time Limit Exceeded"
                    user_process.kill()
                    break
                
                line = user_process.stdout.readline()
                
                if not line:
                    break
                
                line = line.strip()
                
                if not line:
                    continue
                
                if line.startswith("?"):
                    self.query_count += 1
                    
                    # For multi-test: the query limit applies per test case, but we track total
                    # Adjust by dividing by T to check per-case limit
                    effective_limit = self.max_queries if T == 1 else self.max_queries * T
                    if self.query_count > effective_limit:
                        self.verdict = "Query Limit Exceeded"
                        self.message = f"Exceeded {effective_limit} queries (limit is {self.max_queries} per test, {T} tests total)"
                        user_process.kill()
                        break
                    
                    # For multi-test: need to pass which test case we're on
                    response = self._answer_query(line, test_input_data, answer_data, current_test, T)
                    
                    if response is None:
                        self.verdict = "Grader Error"
                        self.message = "Interactor failed"
                        user_process.kill()
                        break
                    
                    try:
                        user_process.stdin.write(response + "\n")
                        user_process.stdin.flush()
                    except (BrokenPipeError, OSError) as e:
                        # User process closed, check if it exited normally
                        if user_process.poll() is not None:
                            # Process exited, stop interaction
                            break
                        else:
                            self.verdict = "Runtime Error"
                            self.message = f"Failed to send response to user: {e}"
                            break
                    except Exception as e:
                        self.verdict = "Runtime Error"
                        self.message = f"Failed to send response to user: {e}"
                        break
                
                elif line.startswith("!"):
                    verdict, message = self._check_answer(line, test_input_data, answer_data, current_test, T)
                    
                    if verdict == "Accepted":
                        test_cases_passed += 1
                        current_test += 1
                        
                        if current_test >= T:
                            # All test cases passed
                            self.verdict = "Accepted"
                            self.message = f"All {T} test case(s) passed" if T > 1 else message
                            self.got_answer = True
                            break
                        else:
                            # Continue to next test case
                            continue
                    else:
                        # Failed on this test case
                        self.verdict = f"Wrong Answer on test {current_test + 1}"
                        self.message = message
                        self.got_answer = True
                        break
                
                else:
                    self.verdict = "Protocol Violation"
                    self.message = f"Output must start with '?' or '!', got: {line[:100]}"
                    user_process.kill()
                    break
            
        except Exception as e:
            self.verdict = "Grader Error"
            self.message = f"Interaction error: {str(e)}"
            try:
                user_process.kill()
            except:
                pass
    
    def _answer_query(self, query: str, test_input: str, answer: str, current_test: int = 0, T: int = 1) -> Optional[str]:
        try:
            # For multi-test: extract the relevant test case from inputs
            if T > 1 and current_test >= 0:
                # Parse test input (skip T, then get test cases)
                test_lines = test_input.strip().split('\n')
                answer_lines = answer.strip().split('\n')
                
                # Get current test case's input and answer
                if current_test < len(test_lines) - 1:
                    test_input_clean = test_lines[current_test + 1] + '\n'
                else:
                    test_input_clean = ''
                
                if current_test < len(answer_lines) - 1:
                    answer_clean = answer_lines[current_test + 1] + '\n'
                else:
                    answer_clean = ''
            else:
                # Single test case: use all input as-is
                test_input_clean = test_input.rstrip('\n') + '\n' if test_input else ''
                answer_clean = answer.rstrip('\n') + '\n' if answer else ''
            
            interactor_input = test_input_clean + answer_clean + query + '\n'
            
            result = subprocess.run(
                self.interactor_cmd,
                input=interactor_input,
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            
            if result.returncode != 0:
                stderr = result.stderr if result.stderr else ""
                logger.error(f"Interactor failed: {stderr}")
                return None
            
            response = result.stdout.strip()
            return response
            
        except subprocess.TimeoutExpired:
            logger.error("Interactor timed out")
            return None
        except Exception as e:
            logger.error(f"Interactor exception: {e}")
            return None
    
    def _check_answer(self, answer: str, test_input: str, secret_answer: str, current_test: int = 0, T: int = 1) -> Tuple[str, str]:
        try:
            # For multi-test: extract the relevant test case from inputs
            if T > 1 and current_test >= 0:
                # Parse test input (skip T, then get test cases)
                test_lines = test_input.strip().split('\n')
                answer_lines = secret_answer.strip().split('\n')
                
                # Get current test case's input and answer
                if current_test < len(test_lines) - 1:
                    test_input_clean = test_lines[current_test + 1] + '\n'
                else:
                    test_input_clean = ''
                
                if current_test < len(answer_lines) - 1:
                    answer_clean = answer_lines[current_test + 1] + '\n'
                else:
                    answer_clean = ''
            else:
                # Single test case: use all input as-is
                test_input_clean = test_input.rstrip('\n') + '\n' if test_input else ''
                answer_clean = secret_answer.rstrip('\n') + '\n' if secret_answer else ''
            
            interactor_input = test_input_clean + answer_clean + answer + '\n'
            
            result = subprocess.run(
                self.interactor_cmd,
                input=interactor_input,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            
            output = result.stdout.strip()
            
            if "AC" in output or "ACCEPTED" in output.upper():
                return "Accepted", output
            elif "WA" in output or "WRONG" in output.upper():
                return "Wrong Answer", output
            elif result.returncode == 0:
                return "Accepted", output
            else:
                return "Wrong Answer", output
                
        except subprocess.TimeoutExpired:
            return "Checker Error", "Interactor timed out"
        except Exception as e:
            return "Checker Error", f"Interactor exception: {str(e)}"


def run_interactive_problem(
    user_executable: str,
    user_lang: str,
    problem_dir: str,
    test_input_path: str,
    time_limit_ms: int,
    memory_limit_mb: int,
) -> Tuple[str, str, int]:
    problem_path = Path(problem_dir)
    
    if user_lang == "cpp":
        user_cmd = [user_executable]
    elif user_lang == "python":
        user_cmd = ["python3", user_executable]
    elif user_lang == "java":
        class_name = Path(user_executable).stem
        user_cmd = ["/usr/bin/java", "-cp", str(Path(user_executable).parent), class_name]
    else:
        return "Grader Error", f"Unsupported language: {user_lang}", 0
    
    interactor_cmd = None
    for ext, lang_cmd in [
        ("interactor.py", ["python3"]),
        ("interactor", []),
        ("interactor.cpp", None),
    ]:
        path = problem_path / ext
        if path.exists():
            if lang_cmd is None:
                continue
            interactor_cmd = lang_cmd + [str(path)]
            break
    
    if not interactor_cmd:
        return "Grader Error", "Interactor not found", 0
    
    test_path = Path(test_input_path)
    answer_filename = test_path.stem + "_answer" + test_path.suffix
    answer_path = problem_path / "answer" / answer_filename

    queries_filename = test_path.stem + "_queries" + test_path.suffix
    queries_path = problem_path / "queries" / queries_filename
    
    runner = InteractiveRunner(
        user_cmd=user_cmd,
        interactor_cmd=interactor_cmd,
        test_input_path=test_input_path,
        answer_path=str(answer_path) if answer_path.exists() else None,
        queries_path=str(queries_path) if queries_path.exists() else None,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
    )
    
    return runner.run()
