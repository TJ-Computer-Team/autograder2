<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api';
  import type { Problem } from '$lib/api.ts';


  let editorEl: HTMLDivElement;
  let aceEditor: any;
  let value = $state('');
  let language = $state('cpp');
  let showEditor = $state(true);
  let textareaEl: HTMLTextAreaElement;

  let problems = $state<Problem[]>([]);
  let selectedProblem = $state<number | null>(null);

  function toggleEditor() {
    showEditor = !showEditor;
    if (showEditor && aceEditor) {
      // Sync textarea value to ace editor when switching to editor
      aceEditor.setValue(value);
      aceEditor.clearSelection();
    } else if (!showEditor) {
      // Sync ace editor value to textarea when switching to textarea
      if (aceEditor) {
        value = aceEditor.getValue();
      }
    }
  }

  function getLanguageMode(lang: string) {
    switch (lang) {
      case 'cpp': return 'c_cpp';
      case 'java': return 'java';
      case 'python': return 'python';
      default: return 'text';
    }
  }

  async function handleSubmit(e: Event) {
    e.preventDefault();
    
    // Get the current code value from active editor
    if (showEditor && aceEditor) {
      value = aceEditor.getValue();
    } else if (!showEditor && textareaEl) {
      value = textareaEl.value;
    }

    if (!selectedProblem || !language || !value.trim()) {
      alert('Please select a problem, language, and enter code.');
      return;
    }
    
    try {
      console.log('Submitting with Value:', value);

      //get the auth cookie token thingy so the post request gooes through
      const match = document.cookie.match(/csrftoken=([^;]+)/);
      const csrfToken = match ? match[1] : '';
      //pos request
      const res = await fetch('http://localhost:3000/status/process_submit/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': csrfToken,
        },
        credentials: 'include',
        body: new URLSearchParams({
          problemid: String(selectedProblem),
          lang: language,
          code: value,
        }),
      });
      //sucessful post -> submissions
      if (res.redirected) {
        window.location.href = '/submissions';
        return;
      }
      //unsucessful post -> alert
      if (!res.ok) {
        const text = await res.text();
        alert('Submission failed: ' + text);
      } else {
        window.location.href = '/submissions';
      }
    } catch (err) {
      alert('Error submitting: ' + err);
    }
  }

  onMount(() => {
    // Load ACE editor and extensions from CDN
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/ace/1.4.14/ace.js';
    script.onload = () => {
      // Load additional ACE extensions
      const extScript = document.createElement('script');
      extScript.src = 'https://cdnjs.cloudflare.com/ajax/libs/ace/1.4.14/ext-language_tools.js';
      extScript.onload = () => {
      // Initialize ACE editor once loaded
      if ((window as any).ace && editorEl) {
        aceEditor = (window as any).ace.edit(editorEl);
        aceEditor.setTheme('ace/theme/monokai');
        aceEditor.session.setMode(`ace/mode/${getLanguageMode(language)}`);
        aceEditor.setOptions({
          fontSize: 14,
          showPrintMargin: false,
          wrap: true,
          autoScrollEditorIntoView: true,
          maxLines: 30,
          minLines: 20,
          enableBasicAutocompletion: true,
          enableSnippets: true,
          enableLiveAutocompletion: false,
          tabSize: 2,
          useSoftTabs: true,
        });
        aceEditor.setValue(value);
        aceEditor.clearSelection();
        
        // Update value and line count when editor content changes
        aceEditor.session.on('change', () => {
          if (showEditor) {
            value = aceEditor.getValue();
            const lineCountEl = document.getElementById('line-count');
            if (lineCountEl) {
              lineCountEl.textContent = aceEditor.session.getLength().toString();
            }
          }
        });

        // Set initial line count
        const lineCountEl = document.getElementById('line-count');
        if (lineCountEl) {
          lineCountEl.textContent = aceEditor.session.getLength().toString();
        }
      }
      };
      document.head.appendChild(extScript);
    };
    document.head.appendChild(script);

    // Fetch problems asynchronously
    (async () => {
      const allProblems = await api.fetchProblemset();
      const contestId = $page.url.searchParams.get('contest');
      if (contestId) {
        problems = allProblems.filter((p) => String(p.contest) === contestId);
      } else {
        problems = allProblems;
      }
      const problemId = $page.url.searchParams.get('problem');
      if (problemId) {
        const prob = problems.find(p => p.id === Number(problemId));
        if (prob) selectedProblem = prob.id;
      } else if (problems.length > 0) selectedProblem = problems[0].id;
    })();

    return () => {
      aceEditor?.destroy?.();
      script.remove();
    };
  });

  $effect(() => {
    if (aceEditor) {
      aceEditor.session.setMode(`ace/mode/${getLanguageMode(language)}`);
    }
  });
</script>

<main class="flex flex-col items-center justify-center min-h-[70vh] px-4 text-white bg-black">
<h1 class="text-2xl font-bold mb-4 pt-8">Submit</h1>
  <div class="w-full max-w-4xl mb-4">
    <div class="mb-4">
      <label for="problem" class="font-semibold text-white mr-2">Problem:</label>
      <select id="problem" bind:value={selectedProblem} class="px-4 py-2 rounded-lg border border-zinc-600 hover:border-indigo-600 text-white bg-zinc-900 transition-all shadow-sm mr-4 inline-block" style="vertical-align: middle;">
      {#each problems as problem}
        <option value={problem.id}>{problem.name}</option>
      {/each}
      </select>
      <label for="lang" class="font-semibold text-white mr-2">Language:</label>
      <select id="lang" bind:value={language} class="px-4 py-2 rounded-lg border border-zinc-600 hover:border-indigo-600 text-white bg-zinc-900 transition-all shadow-sm inline-block" style="vertical-align: middle;">
      <option value="cpp">C++</option>
      <option value="java">Java</option>
      <option value="python">Python</option>  
      </select>
    </div>
    
    {#if language === 'java'}
      <div class="mb-4 p-3 rounded-lg bg-zinc-900 border border-red-500 text-red-300 flex items-center gap-2 shadow">
        <span class="text-red-500 text-xl font-bold">&#33;</span>
        <span>
          Java users: Name your class <span class="font-mono font-bold text-red-400">usercode</span>. <!--<a href="https://docs.google.com/document/d/17r0fh2rezqDhNoCoUtwVtExn8hRml0BjeAqxQZk9MCs/edit?usp=sharing" target="_blank" class="underline text-indigo-400 hover:text-indigo-300">See details</a>-->
        </span>
      </div>
    {/if}

    <!-- Editor Toggle Controls -->
    <div class="mb-0 flex items-center justify-between bg-zinc-800 rounded-t-lg px-4 py-3 border border-zinc-700 border-b-0">
      <div class="flex items-center space-x-4">
        <span class="text-sm font-medium text-zinc-300">Source Code</span>
        <div class="flex items-center space-x-1 bg-zinc-700 rounded-md p-1">
          <button 
            class="px-3 py-1.5 text-xs rounded transition-all font-medium {showEditor ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-400 hover:text-zinc-200'}"
            on:click={toggleEditor}
          >
            Advanced
          </button>
          <button 
            class="px-3 py-1.5 text-xs rounded transition-all font-medium {!showEditor ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-400 hover:text-zinc-200'}"
            on:click={toggleEditor}
          >
            Simple
          </button>
        </div>
      </div>
      <div class="flex items-center space-x-4">
        <div class="text-xs text-zinc-400">
          {showEditor ? 'Syntax highlighting • Auto-completion • Themes' : 'Plain text editor'}
        </div>
        {#if showEditor}
          <div class="text-xs text-zinc-500">
            {language.toUpperCase()}
          </div>
        {/if}
      </div>
    </div>

    <!-- ACE Editor -->
    {#if showEditor}
      <div class="relative">
        <div
          bind:this={editorEl}
          class="w-full border border-zinc-700 border-t-0 rounded-b-lg overflow-hidden"
          style="height: 500px; max-height: 500px;"
        ></div>
        <!-- Editor Status Bar -->
        <div class="absolute bottom-0 right-0 bg-zinc-800 text-zinc-400 px-3 py-1 text-xs rounded-tl-md border-l border-t border-zinc-600">
          Lines: <span class="text-zinc-300" id="line-count">1</span>
        </div>
      </div>
    {/if}

    <!-- Simple Textarea -->
    {#if !showEditor}
      <div class="relative">
        <textarea
          bind:this={textareaEl}
          bind:value={value}
          class="w-full h-[500px] p-4 bg-zinc-900 text-white font-mono text-sm border border-zinc-700 border-t-0 rounded-b-lg resize-none focus:outline-none focus:border-indigo-500 transition-colors leading-relaxed"
          placeholder="Enter your code here..."
          spellcheck="false"
        ></textarea>
        <!-- Textarea Status Bar -->
        <div class="absolute bottom-2 right-2 bg-zinc-800 text-zinc-400 px-2 py-1 text-xs rounded border border-zinc-600">
          {value.split('\n').length} lines • {value.length} chars
        </div>
      </div>
    {/if}
  </div>
  
  <button class="mt-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 px-6 rounded-lg transition-colors" on:click={handleSubmit}>
    Submit
  </button>
</main>