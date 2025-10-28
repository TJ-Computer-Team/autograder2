from django.db import models


class Problem(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    contest = models.ForeignKey("contests.Contest", on_delete=models.CASCADE)
    points = models.IntegerField()
    contest_letter = models.CharField(max_length=1, default="A")

    statement = models.TextField()
    inputtxt = models.TextField()
    outputtxt = models.TextField()
    samples = models.TextField()

    tl = models.IntegerField(null=True, blank=True)
    ml = models.IntegerField(null=True, blank=True)

    interactive = models.BooleanField(default=False)
    secret = models.BooleanField(default=False)

    testcases_zip = models.FileField(upload_to="problem_testcases/", blank=True)

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.interactive and self.testcases_zip:
            self._process_interactive_problem()
    
    def _process_interactive_problem(self):
        import zipfile
        import os
        import subprocess
        from pathlib import Path
        
        problem_dir = Path(f"/home/tjctgrader/problems/{self.id}")
        problem_dir.mkdir(parents=True, exist_ok=True)
        test_dir = problem_dir / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(self.testcases_zip.path, 'r') as zip_ref:
            for file_info in zip_ref.filelist:
                filename = os.path.basename(file_info.filename)
                if not filename:
                    continue
                
                if filename.startswith('interactor.'):
                    interactor_content = zip_ref.read(file_info.filename)
                    
                    if filename.endswith('.py'):
                        interactor_path = problem_dir / "interactor.py"
                        interactor_path.write_bytes(interactor_content)
                        os.chmod(interactor_path, 0o755)
                    
                    elif filename.endswith('.cpp'):
                        cpp_path = problem_dir / "interactor.cpp"
                        cpp_path.write_bytes(interactor_content)
                        
                        result = subprocess.run([
                            '/usr/bin/g++', '-std=c++17', '-O2',
                            '-o', str(problem_dir / 'interactor'),
                            str(cpp_path)
                        ], capture_output=True)
                        
                        if result.returncode == 0:
                            cpp_path.unlink()
                        else:
                            raise Exception(f"C++ compilation failed: {result.stderr.decode()}")
                    
                    elif filename.endswith('.java'):
                        java_path = problem_dir / "Interactor.java"
                        java_path.write_bytes(interactor_content)
                        
                        result = subprocess.run([
                            '/usr/bin/javac', str(java_path)
                        ], capture_output=True, cwd=str(problem_dir))
                        
                        if result.returncode == 0:
                            wrapper_path = problem_dir / "interactor"
                            wrapper_path.write_text(f"#!/bin/bash\njava -cp {problem_dir} Interactor \"$@\"\n")
                            os.chmod(wrapper_path, 0o755)
                        else:
                            raise Exception(f"Java compilation failed: {result.stderr.decode()}")
                
                elif filename.endswith('.txt'):
                    test_content = zip_ref.read(file_info.filename)
                    (test_dir / filename).write_bytes(test_content)