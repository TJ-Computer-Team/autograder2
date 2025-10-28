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
        test_answer_path: Optional[str],
        time_limit_ms: int,
        memory_limit_mb: int,
        test_name: str = "unknown",
    ):
        self.user_cmd = user_cmd
        self.interactor_cmd = interactor_cmd
        self.test_input_path = test_input_path
        self.test_answer_path = test_answer_path
        self.time_limit_ms = time_limit_ms
        self.memory_limit_mb = memory_limit_mb
        self.test_name = test_name
        
        self.test_cases_input = []
        self.test_cases_answer = []
        self.num_test_cases = 0
        self.max_queries_per_tc = []
        
        self.verdict = "Accepted"
        self.message = ""
        self.query_count = 0
        self.start_time = None
        self.got_answer = False
        self.user_process = None
        
    def run(self) -> Tuple[str, str, int]:
        self.start_time = time.time()
        
        if not self._parse_test_files():
            return "Grader Error", "Failed to parse test files", 0
        
        if not self._get_all_max_queries():
            return "Grader Error", "Failed to get max queries from interactor", 0
        
        if not self._start_user_process():
            return "Grader Error", "Failed to start user process", 0
        
        return self._run_interaction()
    
    def _parse_test_files(self) -> bool:
        try:
            if not self.test_input_path or not os.path.exists(self.test_input_path):
                logger.error("Test input file not found")
                return False
            
            with open(self.test_input_path, 'r') as f:
                input_content = f.read().strip()
            
            input_lines = input_content.split('\n')
            if not input_lines:
                return False
            
            self.num_test_cases = int(input_lines[0])
            self.test_cases_input = [input_content]
            
            if self.test_answer_path and os.path.exists(self.test_answer_path):
                with open(self.test_answer_path, 'r') as f:
                    answer_lines = f.read().strip().split('\n')
                
                if answer_lines and int(answer_lines[0]) == self.num_test_cases:
                    self.test_cases_answer = answer_lines[1:]
                else:
                    self.test_cases_answer = ["-"] * self.num_test_cases
            else:
                self.test_cases_answer = ["-"] * self.num_test_cases
            
            return True
            
        except Exception as e:
            logger.error(f"Error parsing test files: {e}")
            return False
    
    def _get_all_max_queries(self) -> bool:
        try:
            for i in range(self.num_test_cases):
                tc_answer = self.test_cases_answer[i] if i < len(self.test_cases_answer) else "-"
                max_q = self._get_max_queries_for_tc(tc_answer)
                if max_q is None:
                    return False
                self.max_queries_per_tc.append(max_q)
            return True
        except Exception as e:
            logger.error(f"Error getting max queries: {e}")
            return False
    
    def _get_max_queries_for_tc(self, tc_answer: str) -> Optional[int]:
        try:
            result = subprocess.run(
                self.interactor_cmd,
                input=f"{tc_answer}\nMAX_QUERIES\n",
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            
            if result.returncode != 0:
                logger.error(f"Interactor failed: {result.stderr}")
                return None
            
            return int(result.stdout.strip())
        except ValueError:
            logger.error(f"Interactor returned non-integer: {result.stdout.strip()}")
            return None
        except subprocess.TimeoutExpired:
            logger.error("Interactor timed out getting max queries")
            return None
        except Exception as e:
            logger.error(f"Interactor exception: {e}")
            return None
    
    def _start_user_process(self) -> bool:
        try:
            self.user_process = subprocess.Popen(
                self.user_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            
            input_data = f"{self.num_test_cases}\n"
            for tc_input in self.test_cases_input:
                input_data += tc_input
            
            self.user_process.stdin.write(input_data)
            self.user_process.stdin.flush()
            return True
        except Exception as e:
            logger.error(f"Failed to start user process: {e}")
            return False
    
    def _run_interaction(self) -> Tuple[str, str, int]:
        try:
            interaction_thread = threading.Thread(
                target=self._interact_all_test_cases,
                daemon=True
            )
            interaction_thread.start()
            
            timeout_seconds = self.time_limit_ms / 1000.0
            interaction_thread.join(timeout=timeout_seconds)
            
            elapsed_ms = int((time.time() - self.start_time) * 1000)
            
            if interaction_thread.is_alive():
                self.user_process.kill()
                return "Time Limit Exceeded", "", min(elapsed_ms, self.time_limit_ms)
            
            if self.user_process.returncode and self.user_process.returncode != 0:
                stderr = self.user_process.stderr.read() if self.user_process.stderr else ""
                return "Runtime Error", stderr[:1000], elapsed_ms
            
            return self.verdict, self.message, elapsed_ms
            
        except Exception as e:
            elapsed_ms = int((time.time() - self.start_time) * 1000)
            return "Grader Error", f"Exception: {str(e)}", elapsed_ms
    
    def _interact_all_test_cases(self):
        try:
            for tc_idx in range(self.num_test_cases):
                self.query_count = 0
                self.got_answer = False
                
                if not self._interact_single_test_case(tc_idx):
                    break
                
                if self.verdict != "Accepted":
                    break
            
        except Exception as e:
            self.verdict = "Grader Error"
            self.message = f"Interaction error: {str(e)}"
            try:
                self.user_process.kill()
            except:
                pass
    
    def _interact_single_test_case(self, tc_idx: int) -> bool:
        max_queries = self.max_queries_per_tc[tc_idx]
        tc_answer = self.test_cases_answer[tc_idx] if tc_idx < len(self.test_cases_answer) else "-"
        
        try:
            while True:
                if (time.time() - self.start_time) * 1000 >= self.time_limit_ms:
                    self.verdict = "Time Limit Exceeded"
                    self.user_process.kill()
                    return False
                
                line = self.user_process.stdout.readline()
                if not line:
                    if not self.got_answer:
                        self.verdict = "Runtime Error"
                        self.message = f"Program exited without submitting answer for test case {tc_idx + 1}"
                    return False
                
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith("?"):
                    if not self._handle_query(line, tc_answer, max_queries, tc_idx):
                        return False
                        
                elif line.startswith("!"):
                    return self._handle_answer(line, tc_answer, tc_idx)
                    
                else:
                    self.verdict = "Protocol Violation"
                    self.message = f"Output must start with '?' or '!', got: {line[:100]}"
                    self.user_process.kill()
                    return False
            
        except Exception as e:
            self.verdict = "Grader Error"
            self.message = f"Interaction error on test case {tc_idx + 1}: {str(e)}"
            return False
    
    def _handle_query(self, query: str, tc_answer: str, max_queries: int, tc_idx: int) -> bool:
        self.query_count += 1
        
        if self.query_count > max_queries:
            self.verdict = f"Idleness Limit Exceeded on test {self.test_name}"
            self.message = f"Exceeded {max_queries} queries on test case {tc_idx + 1}"
            self.user_process.kill()
            return False
        
        response = self._call_interactor(query, tc_answer)
        if response is None:
            self.verdict = "Grader Error"
            self.message = f"Interactor failed on test case {tc_idx + 1}"
            self.user_process.kill()
            return False
        
        try:
            self.user_process.stdin.write(response + "\n")
            self.user_process.stdin.flush()
            return True
        except Exception as e:
            self.verdict = "Runtime Error"
            self.message = f"Failed to send response to user: {e}"
            return False
    
    def _handle_answer(self, answer: str, tc_answer: str, tc_idx: int) -> bool:
        verdict, message = self._check_answer(answer, tc_answer)
        if verdict != "Accepted":
            self.verdict = verdict
            self.message = f"Test case {tc_idx + 1}: {message}"
            return False
        self.got_answer = True
        return True
    
    def _call_interactor(self, query: str, tc_answer: str) -> Optional[str]:
        try:
            result = subprocess.run(
                self.interactor_cmd,
                input=f"{tc_answer}\n{query}\n",
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            
            if result.returncode != 0:
                logger.error(f"Interactor failed: {result.stderr}")
                return None
            
            return result.stdout.strip()
            
        except subprocess.TimeoutExpired:
            logger.error("Interactor timed out")
            return None
        except Exception as e:
            logger.error(f"Interactor exception: {e}")
            return None
    
    def _check_answer(self, answer: str, tc_answer: str) -> Tuple[str, str]:
        try:
            result = subprocess.run(
                self.interactor_cmd,
                input=f"{tc_answer}\n{answer}\n",
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
    
    for ext, lang_cmd in [
        ("interactor.py", ["python3"]),
        ("interactor", []),
    ]:
        path = problem_path / ext
        if path.exists():
            interactor_cmd = lang_cmd + [str(path)]
            break
    else:
        return "Grader Error", "Interactor not found", 0
    
    test_input_pathobj = Path(test_input_path)
    test_answer_path = test_input_pathobj.parent / (test_input_pathobj.stem + "_answer.txt")
    
    runner = InteractiveRunner(
        user_cmd=user_cmd,
        interactor_cmd=interactor_cmd,
        test_input_path=test_input_path,
        test_answer_path=str(test_answer_path) if test_answer_path.exists() else None,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        test_name=test_name,
    )
    
    return runner.run()
