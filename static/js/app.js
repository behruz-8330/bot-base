let editor;
let currentFilePath = "";
const tg = window.Telegram.WebApp;
tg.expand();

require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min' }});
require(['vs/editor/editor.main'], function() {
    editor = monaco.editor.create(document.getElementById('editor'), {
        value: '# Tahrirlash uchun chapdan faylni tanlang (app.py, requirements.txt va h.k.)...',
        language: 'python',
        theme: 'vs-dark',
        automaticLayout: true,
        fontSize: 14
    });
    loadFiles("");
});

async function loadFiles(path) {
    try {
        const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
        const items = await res.json();
        const listDiv = document.getElementById('file-list');
        listDiv.innerHTML = "";

        if (path) {
            let parentPath = path.split('/').slice(0, -1).join('/');
            let div = document.createElement('div');
            div.className = 'file-item';
            div.innerHTML = `📁 <b>.. Orqaga</b>`;
            div.onclick = () => loadFiles(parentPath);
            listDiv.appendChild(div);
        }

        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'file-item';
            div.innerHTML = item.is_dir ? `📁 ${item.name}` : `📄 ${item.name}`;
            div.onclick = () => {
                if (item.is_dir) {
                    loadFiles(item.path);
                } else {
                    openFile(item.path);
                }
            };
            listDiv.appendChild(div);
        });
    } catch (e) {
        console.error("Fayllarni yuklashda xato:", e);
    }
}

async function openFile(path) {
    currentFilePath = path;
    document.getElementById('current-file').innerText = path;
    try {
        const res = await fetch(`/api/read?path=${encodeURIComponent(path)}`);
        const data = await res.json();
        
        // Har qanday fayl turiga qarab dasturlash tilini real vaqtda moslash
        let lang = 'python';
        if (path.endsWith('.js')) lang = 'javascript';
        else if (path.endsWith('.json')) lang = 'json';
        else if (path.endsWith('.html')) lang = 'html';
        else if (path.endsWith('.css')) lang = 'css';
        else if (path.endsWith('.md')) lang = 'markdown';
        else if (path.endsWith('.txt') || path.endsWith('.env')) lang = 'plaintext';

        monaco.editor.setModelLanguage(editor.getModel(), lang);
        editor.setValue(data.content);
    } catch (e) {
        console.error("Faylni o'qishda xato:", e);
    }
}

async function saveFile() {
    if (!currentFilePath) {
        tg.showAlert("Avval faylni tanlang!");
        return;
    }
    const content = editor.getValue();
    
    try {
        const res = await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentFilePath, content: content })
        });

        if (res.ok) {
            tg.HapticFeedback.notificationOccurred('success');
            tg.showAlert("Muvaffaqiyatli saqlandi! ✅");
        } else {
            tg.HapticFeedback.notificationOccurred('error');
            tg.showAlert("Saqlashda xatolik yuz berdi ❌");
        }
    } catch (e) {
        console.error("Saqlashda tarmoq xatosi:", e);
    }
}
