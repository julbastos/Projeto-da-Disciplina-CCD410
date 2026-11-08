const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let books = [], readers = [], loans = [];

function notice(message, error=false) {
  $('#notice').textContent = message;
  $('#notice').className = error ? 'error' : '';
  $('#notice').hidden = false;
}

async function api(path, method='GET', data) {
  const response = await fetch('/api'+path, {
    method,
    headers: {'Content-Type':'application/json'},
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const value = await response.json();
  if (!response.ok) throw Error(typeof value.detail === 'string' ? value.detail : 'verifique os campos informados.');
  return value;
}

const empty = message => `<div class="empty">${message}</div>`;
const deleteButton = (kind, id) => `<button data-delete-kind="${kind}" data-delete-id="${esc(id)}">excluir</button>`;

function renderBooks() {
  const q = $('#busca').value.toLocaleLowerCase();
  const items = books.filter(b => [b.titulo,...b.autores,...b.generos].some(v => v.toLocaleLowerCase().includes(q)));
  $('#book-count').textContent = `(${items.length})`;
  $('#books').innerHTML = items.length ? items.map(b => `
    <article class="book">
      <div class="cover"><span>${esc(b.titulo)}</span></div>
      <div class="book-info">
        <h3>${esc(b.titulo)}</h3>
        <p>${esc(b.autores.join(', '))}</p>
        <p>${esc(b.generos.join(' · '))}${b.ano ? ' / '+esc(b.ano) : ''}</p>
        <p>isbn: ${esc(b.isbn || 'não informado')}</p>
        <div class="book-bottom"><span>${b.quantidade} disponíveis</span><button data-stock="${esc(b.id)}">estoque</button></div>
        <div class="actions"><button data-edit-book="${esc(b.id)}">editar</button>${deleteButton('livros',b.id)}</div>
      </div>
    </article>`).join('') : empty('nenhum livro encontrado.');
}

function renderReaders() {
  $('#readers').innerHTML = readers.length ? `
    <table><thead><tr><th>id</th><th>leitor</th><th>email</th><th>telefone</th><th>matrícula</th><th>ações</th></tr></thead>
      <tbody>${readers.map(u => `<tr><td>${u.id}</td><td>${esc(u.nome)}</td><td>${esc(u.email)}</td>
        <td>${esc(u.telefone || '—')}</td><td>${esc(u.matricula || '—')}</td>
        <td><div class="actions"><button data-edit-reader="${u.id}">editar</button>${deleteButton('usuarios',u.id)}</div></td>
      </tr>`).join('')}</tbody>
    </table>` : empty('nenhum leitor cadastrado.');
}

function renderLoans() {
  $('#loans').innerHTML = loans.length ? `
    <table><thead><tr><th>livro</th><th>leitor</th><th>data</th><th>situação</th><th>histórico</th><th>ações</th></tr></thead>
      <tbody>${loans.map(l => `<tr>
        <td>${esc(books.find(b => b.id === l.livro_id)?.titulo || l.livro_id)}</td><td>${esc(l.usuario_nome)}</td>
        <td>${new Date(l.criado_em).toLocaleDateString('pt-BR')}</td><td>${l.devolvido ? 'devolvido' : 'emprestado'}</td>
        <td>${l.sincronizado ? 'atualizado' : 'pendente'}</td>
        <td><div class="actions"><button data-loan-state="${esc(l.id)}">${l.devolvido ? 'reabrir' : 'devolver'}</button>${deleteButton('emprestimos',l.id)}</div></td>
      </tr>`).join('')}</tbody>
    </table>` : empty('nenhum empréstimo registrado.');
}

async function refresh() {
  const results = await Promise.allSettled([api('/livros'),api('/usuarios'),api('/emprestimos')]);
  results.forEach((r,i) => {
    if (r.status === 'fulfilled') {
      if (i === 0) { books = r.value; renderBooks(); }
      if (i === 1) { readers = r.value; renderReaders(); }
      if (i === 2) { loans = r.value; renderLoans(); }
    } else {
      const target = ['#books','#readers','#loans'][i];
      $(target).innerHTML = empty('não foi possível carregar. verifique as conexões e recarregue a página.');
      notice(r.reason.message,true);
    }
  });
  if (results[0].status === 'fulfilled' && results[2].status === 'fulfilled') renderLoans();
  $('#loan-reader').innerHTML = '<option value="">selecione um leitor</option>'+readers.map(u => `<option value="${u.id}">${esc(u.nome)}</option>`).join('');
  $('#loan-book').innerHTML = '<option value="">selecione um livro</option>'+books.filter(b => b.quantidade > 0).map(b => `<option value="${esc(b.id)}">${esc(b.titulo)} (${b.quantidade})</option>`).join('');
}

function openEditor(type, id) {
  const form = $('#'+type+'-form');
  form.reset();
  form.dataset.editId = id || '';
  form.querySelector('.form-error').textContent = '';
  form.querySelector('h2').textContent = type === 'livro' ? (id ? 'editar livro' : 'cadastrar livro') : (id ? 'editar leitor' : 'cadastrar leitor');
  form.querySelector('.primary').textContent = id ? 'salvar' : 'cadastrar';
  if (id) {
    const item = (type === 'livro' ? books : readers).find(item => String(item.id) === String(id));
    for (const [name,value] of Object.entries(item)) {
      if (form.elements.namedItem(name)) form.elements.namedItem(name).value = Array.isArray(value) ? value.join(', ') : (value ?? '');
    }
  }
  form.closest('dialog').showModal();
}

const titles = {acervo:'livros',usuarios:'leitores',emprestimos:'empréstimos'};
document.addEventListener('click', async e => {
  const button = e.target.closest('button');
  if (!button) return;
  if (button.dataset.tab) {
    const tab = button.dataset.tab;
    document.querySelectorAll('.panel').forEach(p => p.hidden = p.id !== tab);
    document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active',b === button));
    $('#title').textContent = titles[tab];
    $('#breadcrumb').textContent = titles[tab];
  }
  if (button.dataset.dialog === 'livro-dialog') openEditor('livro');
  else if (button.dataset.dialog === 'usuario-dialog') openEditor('usuario');
  else if (button.dataset.dialog) {
    const dialog = $('#'+button.dataset.dialog);
    dialog.querySelector('.form-error').textContent = '';
    dialog.showModal();
  }
  if (button.hasAttribute('data-close')) button.closest('dialog').close();
  if (button.dataset.editBook) openEditor('livro',button.dataset.editBook);
  if (button.dataset.editReader) openEditor('usuario',button.dataset.editReader);
  if (button.dataset.stock) {
    const book = books.find(b => b.id === button.dataset.stock);
    $('#estoque-form').elements.livro_id.value = book.id;
    $('#estoque-form').elements.quantidade.value = book.quantidade;
    $('#estoque-form .form-error').textContent = '';
    $('#estoque-dialog').showModal();
  }
  if (button.dataset.deleteKind) {
    if (!confirm('excluir este registro?')) return;
    button.disabled = true;
    try {
      const result = await api('/'+button.dataset.deleteKind+'/'+button.dataset.deleteId,'DELETE');
      notice(result.detail);
      await refresh();
    } catch (error) { notice(error.message,true); }
    finally { button.disabled = false; }
  }
  if (button.dataset.loanState) {
    const loan = loans.find(l => l.id === button.dataset.loanState);
    button.disabled = true;
    try {
      await api('/emprestimos/'+loan.id,'PUT',{devolvido:!loan.devolvido});
      notice(loan.devolvido ? 'empréstimo reaberto.' : 'devolução registrada.');
      await refresh();
    } catch (error) { notice(error.message,true); }
    finally { button.disabled = false; }
  }
});

$('#busca').addEventListener('input',renderBooks);
function bindForm(id, send) {
  $(id).addEventListener('submit', async e => {
    e.preventDefault();
    const form = e.target, button = form.querySelector('button.primary');
    button.disabled = true;
    form.querySelector('.form-error').textContent = '';
    try {
      await send(Object.fromEntries(new FormData(form)),form.dataset.editId);
      form.closest('dialog').close();
      form.reset();
      notice('registro salvo.');
      await refresh();
    } catch (error) { form.querySelector('.form-error').textContent = error.message; }
    finally { button.disabled = false; }
  });
}
bindForm('#usuario-form',(d,id) => api('/usuarios'+(id ? '/'+id : ''),id ? 'PUT' : 'POST',d));
bindForm('#livro-form',(d,id) => api('/livros'+(id ? '/'+id : ''),id ? 'PUT' : 'POST',{
  ...d,autores:d.autores.split(','),generos:d.generos.split(','),
  ano:d.ano ? Number(d.ano) : null,isbn:d.isbn || null,quantidade:Number(d.quantidade),
}));
bindForm('#emprestimo-form',d => api('/emprestimos','POST',{...d,usuario_id:Number(d.usuario_id)}));
bindForm('#estoque-form',d => api('/livros/'+d.livro_id+'/estoque','PUT',{quantidade:Number(d.quantidade)}));
$('#sync').onclick = async e => {
  e.target.disabled = true;
  try {
    const result = await api('/sincronizar','POST');
    notice(`${result.sincronizados} registros atualizados.`);
    await refresh();
  } catch (error) { notice(error.message,true); }
  finally { e.target.disabled = false; }
};
refresh();
