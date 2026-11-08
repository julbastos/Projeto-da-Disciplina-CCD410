const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let books = [], readers = [], loans = [];
function notice(message, error=false) { $('#notice').textContent=message; $('#notice').className=error?'error':''; $('#notice').hidden=false; }
async function api(path, method='GET', data) {
  const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
  const value=await response.json();
  if(!response.ok) throw Error(typeof value.detail==='string'?value.detail:'verifique os campos informados.');
  return value;
}
const empty = message => `<div class="empty">${message}</div>`;
function renderBooks(items=books) {
  $('#book-count').textContent=`(${items.length})`;
  $('#books').innerHTML=items.length?items.map(b=>`<article class="book"><div class="cover"><span>${esc(b.titulo)}</span></div><div class="book-info"><h3>${esc(b.titulo)}</h3><p>${esc(b.autores.join(', '))}</p><p>${esc(b.generos.join(' · '))}${b.ano?' / '+esc(b.ano):''}</p><p>isbn: ${esc(b.isbn||'não informado')}</p><div class="book-bottom"><span>${b.quantidade} disponíveis</span><button data-stock="${esc(b.id)}">ajustar estoque</button></div></div></article>`).join(''):empty('nenhum livro encontrado.');
}
function renderReaders() {
  $('#readers').innerHTML=readers.length?`<table><thead><tr><th>id</th><th>leitor</th><th>email</th><th>telefone</th><th>matrícula</th></tr></thead><tbody>${readers.map(u=>`<tr><td>${u.id}</td><td>${esc(u.nome)}</td><td>${esc(u.email)}</td><td>${esc(u.telefone||'—')}</td><td>${esc(u.matricula||'—')}</td></tr>`).join('')}</tbody></table>`:empty('nenhum leitor cadastrado.');
}
function renderLoans() {
  $('#loans').innerHTML=loans.length?`<table><thead><tr><th>livro</th><th>leitor</th><th>data</th><th>situação</th><th>cassandra</th><th>ação</th></tr></thead><tbody>${loans.map(l=>`<tr><td>${esc(books.find(b=>b.id===l.livro_id)?.titulo||l.livro_id)}</td><td>${esc(l.usuario_nome)}</td><td>${new Date(l.criado_em).toLocaleDateString('pt-BR')}</td><td>${l.devolvido?'devolvido':'emprestado'}</td><td>${l.sincronizado?'sincronizado':'pendente'}</td><td>${l.devolvido?'—':`<button data-return="${esc(l.id)}">devolver</button>`}</td></tr>`).join('')}</tbody></table>`:empty('nenhum empréstimo registrado.');
}
async function refresh() {
  const results=await Promise.allSettled([api('/livros'),api('/usuarios'),api('/emprestimos')]);
  results.forEach((r,i)=>{if(r.status==='fulfilled'){if(i===0){books=r.value;renderBooks();}if(i===1){readers=r.value;renderReaders();}if(i===2){loans=r.value;renderLoans();}}else{const target=['#books','#readers','#loans'][i];$(target).innerHTML=empty('não foi possível carregar. verifique os bancos e recarregue a página.');notice(r.reason.message,true);}});
  if(results[0].status==='fulfilled'&&results[2].status==='fulfilled') renderLoans();
  $('#loan-reader').innerHTML='<option value="">selecione um leitor</option>'+readers.map(u=>`<option value="${u.id}">${esc(u.nome)}</option>`).join('');
  $('#loan-book').innerHTML='<option value="">selecione um livro</option>'+books.filter(b=>b.quantidade>0).map(b=>`<option value="${esc(b.id)}">${esc(b.titulo)} (${b.quantidade})</option>`).join('');
}
const titles={acervo:'livros',usuarios:'leitores',emprestimos:'empréstimos',bancos:'bancos de dados'};
document.addEventListener('click', async e=>{
  const button=e.target.closest('button'); if(!button)return;
  if(button.dataset.tab){const tab=button.dataset.tab;document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!==tab);document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b===button));$('#title').textContent=titles[tab];$('#breadcrumb').textContent=titles[tab];}
  if(button.dataset.dialog) $('#'+button.dataset.dialog).showModal();
  if(button.hasAttribute('data-close')) button.closest('dialog').close();
  if(button.dataset.stock){const book=books.find(b=>b.id===button.dataset.stock);$('#estoque-form').elements.livro_id.value=book.id;$('#estoque-form').elements.quantidade.value=book.quantidade;$('#estoque-dialog').showModal();}
  if(button.dataset.return){button.disabled=true;try{await api('/emprestimos/'+button.dataset.return+'/devolucao','POST');notice('devolução registrada.');await refresh();}catch(error){notice(error.message,true);}finally{button.disabled=false;}}
});
$('#busca').addEventListener('input', e=>{const q=e.target.value.toLocaleLowerCase();renderBooks(books.filter(b=>[b.titulo,...b.autores,...b.generos].some(v=>v.toLocaleLowerCase().includes(q))));});
function bindForm(id, send) { $(id).addEventListener('submit',async e=>{e.preventDefault();const form=e.target,button=form.querySelector('button.primary');button.disabled=true;form.querySelector('.form-error').textContent='';try{await send(Object.fromEntries(new FormData(form)));form.closest('dialog').close();form.reset();notice('operação concluída.');await refresh();}catch(error){form.querySelector('.form-error').textContent=error.message;}finally{button.disabled=false;}}); }
bindForm('#usuario-form', d=>api('/usuarios','POST',d));
bindForm('#livro-form', d=>api('/livros','POST',{...d,autores:d.autores.split(','),generos:d.generos.split(','),ano:d.ano?Number(d.ano):null,isbn:d.isbn||null,quantidade:Number(d.quantidade)}));
bindForm('#emprestimo-form', d=>api('/emprestimos','POST',{...d,usuario_id:Number(d.usuario_id)}));
bindForm('#estoque-form', d=>api('/livros/'+d.livro_id+'/estoque','PUT',{quantidade:Number(d.quantidade)}));
$('#sync').onclick=async e=>{e.target.disabled=true;try{const result=await api('/sincronizar','POST');notice(`${result.sincronizados} registros sincronizados.`);await refresh();}catch(error){notice(error.message,true);}finally{e.target.disabled=false;}};
$('#check-health').onclick=async e=>{e.target.disabled=true;try{const result=await api('/saude');Object.entries(result).forEach(([k,v])=>$('#'+k).textContent=v);}catch(error){notice(error.message,true);}finally{e.target.disabled=false;}};
$('#history-form').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));const button=e.target.querySelector('button');button.disabled=true;try{$('#history-result').textContent=JSON.stringify(await api('/historico/'+d.tipo+'/'+encodeURIComponent(d.id)),null,2);}catch(error){$('#history-result').textContent=error.message;}finally{button.disabled=false;}};
refresh();
