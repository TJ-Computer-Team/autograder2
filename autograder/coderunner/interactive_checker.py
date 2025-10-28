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
        time_limit_ms: int,
        memory_limit_mb: int,
        test_name: str = "unknown",
    ):
        self.user_cmd = user_cmd
        self.interactor_cmd = interactor_cmd
        self.test_input_path = test_input_path
        self.time_limit_ms = time_limit_ms
        self.memory_limit_mb = memory_limit_mb
        self.test_name = test_name
        self.max_queries = None
        
        self.verdict = "Accepted"
        self.message = ""
        self.query_count = 0
        self.start_time = None
        self.got_answer = False
        
    def run(self) -> Tuple[str, str, int]:
        self.start_time = time.time()
        
        test_input_data = ""
        if self.test_input_path and os.path.exists(self.test_input_path):
            with open(self.test_input_path, 'r') as f:
                test_input_data = f.read()
        
        self.max_queries = self._get_max_queries(test_input_data)
        if self.max_queries is None:
            return "Grader Error", "Failed to get max queries from interactor", 0
        
        try:
            user_process = subprocess.Popen(
                self.user_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            
            interaction_thread = threading.Thread(
                target=self._interact,
                args=(user_process, test_input_data),
                daemon=True
            )
            interaction_thread.start()
            
            timeout_seconds = self.time_limit_ms / 1000.0
            interaction_thread.join(timeout=timeout_seconds)
            
            elapsed_ms = int((time.time() - self.start_time) * 1000)
            
            if interaction_thread.is_alive():
                user_process.kill()
                return "Time Limit Exceeded", "", min(elapsed_ms, self.time_limit_ms)
            
            if user_process.returncode and user_process.returncode != 0:
                stderr = user_process.stderr.read() if user_process.stderr else ""
                return "Runtime Error", stderr[:1000], elapsed_ms
            
            if not self.got_answer and self.verdict == "Accepted":
                return "Runtime Error", "Program exited without submitting answer", elapsed_ms
            
            return self.verdict, self.message, elapsed_ms
            
        except Exception as e:
            elapsed_ms = int((time.time() - self.start_time) * 1000)
            return "Grader Error", f"Exception: {str(e)}", elapsed_ms
    
    def _interact(self, user_process, test_input_data):
        try:
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
                    
                    if self.query_count > self.max_queries:
                        self.verdict = f"Idleness Limit Exceeded on test {self.test_name}"
                        self.message = f"Exceeded {self.max_queries} queries"
                        user_process.kill()
                        break
                    
                    response = self._answer_query(line, test_input_data)
                    
                    if response is None:
                        self.verdict = "Grader Error"
                        self.message = "Interactor failed"
                        user_process.kill()
                        break
                    
                    try:
                        user_process.stdin.write(response + "\n")
                        user_process.stdin.flush()
                    except Exception as e:
                        self.verdict = "Runtime Error"
                        self.message = f"Failed to send response to user: {e}"
                        break
                
                elif line.startswith("!"):
                    verdict, message = self._check_answer(line, test_input_data)
                    self.verdict = verdict
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
    
    def _get_max_queries(self, test_input: str) -> Optional[int]:
        try:
            test_input_clean = test_input.rstrip('\n') + '\n' if test_input else ''
            interactor_input = test_input_clean + 'MAX_QUERIES\n'
            
            result = subprocess.run(
                self.interactor_cmd,
                input=interactor_input,
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            
            if result.returncode != 0:
                stderr = result.stderr if result.stderr else ""
                logger.error(f"Interactor failed to get max queries: {stderr}")
                return None
            
            response = result.stdout.strip()
            try:
                max_queries = int(response)
                return max_queries
            except ValueError:
                logger.error(f"Interactor returned non-integer max queries: {response}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("Interactor timed out getting max queries")
            return None
        except Exception as e:
            logger.error(f"Interactor exception getting max queries: {e}")
            return None
    
    def _answer_query(self, query: str, test_input: str) -> Optional[str]:
        try:
            test_input_clean = test_input.rstrip('\n') + '\n' if test_input else ''
            interactor_input = test_input_clean + query + '\n'
            
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
    
    def _check_answer(self, answer: str, test_input: str) -> Tuple[str, str]:
        try:
            test_input_clean = test_input.rstrip('\n') + '\n' if test_input else ''
            interactor_input = test_input_clean + answer + '\n'
            
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
    test_name: str = "unknown",
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
    
    runner = InteractiveRunner(
        user_cmd=user_cmd,
        interactor_cmd=interactor_cmd,
        test_input_path=test_input_path,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        test_name=test_name,
    )
    
    return runner.run()
