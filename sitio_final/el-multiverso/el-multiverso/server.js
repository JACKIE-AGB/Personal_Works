// ============================================================
//  El Multiverso - Servidor Node.js (Express)
//  Datos guardados en /data/*.json (se crean solos al iniciar)
// ============================================================
const express = require('express');
const session = require('express-session');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const app = express();
const PORT = process.env.PORT || 3000;
const DATA = path.join(__dirname, 'data');
const F_USUARIOS = path.join(DATA, 'usuarios.json');
const F_PEDIDOS = path.join(DATA, 'pedidos.json');

// ---------- Utilidades de almacenamiento ----------
fs.mkdirSync(DATA, { recursive: true });
const leer = f => JSON.parse(fs.readFileSync(f, 'utf8'));
const guardar = (f, d) => {
  fs.writeFileSync(f + '.tmp', JSON.stringify(d, null, 2));
  fs.renameSync(f + '.tmp', f);
};

// ---------- Contraseñas (scrypt, incluido en Node) ----------
const hashPass = (p, salt = crypto.randomBytes(16).toString('hex')) =>
  salt + ':' + crypto.scryptSync(p, salt, 64).toString('hex');
const verificarPass = (p, guardado) => {
  const [salt, h] = guardado.split(':');
  const a = Buffer.from(h, 'hex');
  const b = crypto.scryptSync(p, salt, 64);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
};

// ---------- Datos iniciales: 2 cuentas desde el inicio ----------
if (!fs.existsSync(F_USUARIOS)) {
  guardar(F_USUARIOS, [
    { id: '0000', nombre: 'Administrador', paterno: 'Sistema', materno: '', edad: 30, sexo: 'Masculino',
      tipo: 'PT', correo: 'admin@elmultiverso.com', telefono: '0000000000', password: hashPass('Progweb2#') },
    { id: '9999', nombre: 'Cliente', paterno: 'Demo', materno: '', edad: 25, sexo: 'Masculino',
      tipo: 'CT', correo: 'cliente@elmultiverso.com', telefono: '0000000000', password: hashPass('Progweb2#') }
  ]);
}
if (!fs.existsSync(F_PEDIDOS)) guardar(F_PEDIDOS, []);

// ---------- Middleware ----------
app.use(express.json());
app.use(session({
  secret: process.env.SESSION_SECRET || 'el-multiverso-cambia-este-secreto',
  resave: false, saveUninitialized: false,
  cookie: { httpOnly: true, sameSite: 'lax', maxAge: 1000 * 60 * 60 * 8 }
}));

// Protección de páginas HTML según sesión y tipo de usuario
app.use((req, res, next) => {
  const u = req.session.usuario;
  const p = req.path;
  if (['/registrar-pedido.html', '/consultar-pedidos.html'].includes(p) && !u) return res.redirect('/login.html');
  if (p === '/administrar-pedidos.html' && (!u || u.tipo !== 'PT')) return res.redirect(u ? '/' : '/login.html');
  if (['/login.html', '/registro.html'].includes(p) && u) return res.redirect('/');
  next();
});
app.use(express.static(path.join(__dirname, 'public')));

// ---------- Guardas de API ----------
const requiereSesion = (req, res, next) =>
  req.session.usuario ? next() : res.status(401).json({ error: 'Debes iniciar sesión.' });
const requiereAdmin = (req, res, next) =>
  req.session.usuario && req.session.usuario.tipo === 'PT' ? next() : res.status(403).json({ error: 'Acceso solo para administradores.' });

// ---------- Validaciones ----------
const RE_PASS = /^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$/;
const RE_MAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const txt = v => (typeof v === 'string' ? v.trim() : '');

function validarPedido(b) {
  const idProducto = txt(b.idProducto), producto = txt(b.producto), marca = txt(b.marca), unidad = txt(b.unidad);
  const precio = Number(b.precio);
  if (!idProducto || !producto || !marca || !unidad) return { error: 'Completa todos los campos del pedido.' };
  if (!Number.isFinite(precio) || precio < 0) return { error: 'El precio debe ser un número válido.' };
  return { ok: { idProducto, producto, marca, unidad, precio: Math.round(precio * 100) / 100 } };
}

// ---------- API: sesión ----------
app.get('/api/me', (req, res) => res.json({ usuario: req.session.usuario || null }));

app.post('/api/login', (req, res) => {
  const id = txt(req.body.id), pass = typeof req.body.password === 'string' ? req.body.password : '';
  const u = leer(F_USUARIOS).find(x => x.id === id);
  if (!u || !verificarPass(pass, u.password)) return res.status(401).json({ error: 'ID de usuario o contraseña incorrectos.' });
  req.session.usuario = { id: u.id, tipo: u.tipo, nombre: u.nombre };
  res.json({ usuario: req.session.usuario });
});

app.post('/api/logout', (req, res) => req.session.destroy(() => res.json({ ok: true })));

// ---------- API: registro de usuarios ----------
app.post('/api/registro', (req, res) => {
  const b = req.body;
  const u = {
    id: txt(b.id), nombre: txt(b.nombre), paterno: txt(b.paterno), materno: txt(b.materno),
    edad: Number(b.edad), sexo: txt(b.sexo), tipo: txt(b.tipo), correo: txt(b.correo), telefono: txt(b.telefono)
  };
  const pass = typeof b.password === 'string' ? b.password : '';
  if (!/^\d{4}$/.test(u.id)) return res.status(400).json({ error: 'El ID de usuario debe tener 4 dígitos.' });
  if (!u.nombre || !u.paterno || !u.materno) return res.status(400).json({ error: 'Nombre y apellidos son obligatorios.' });
  if (!Number.isInteger(u.edad) || u.edad < 1 || u.edad > 120) return res.status(400).json({ error: 'Ingresa una edad válida.' });
  if (!['Masculino', 'Femenino', 'Otro'].includes(u.sexo)) return res.status(400).json({ error: 'Selecciona el sexo.' });
  if (!['CT', 'PT'].includes(u.tipo)) return res.status(400).json({ error: 'Selecciona el tipo de usuario.' });
  if (!RE_MAIL.test(u.correo)) return res.status(400).json({ error: 'Correo electrónico no válido.' });
  if (!/^\d{10}$/.test(u.telefono)) return res.status(400).json({ error: 'El teléfono debe tener 10 dígitos.' });
  if (!RE_PASS.test(pass)) return res.status(400).json({ error: 'La contraseña debe tener mínimo 8 caracteres, una mayúscula, un número y un símbolo.' });
  if (pass !== b.confirmar) return res.status(400).json({ error: 'Las contraseñas no coinciden.' });

  const usuarios = leer(F_USUARIOS);
  if (usuarios.some(x => x.id === u.id)) return res.status(409).json({ error: 'Ese ID de usuario ya está registrado.' });
  usuarios.push({ ...u, password: hashPass(pass) });
  guardar(F_USUARIOS, usuarios);
  res.status(201).json({ ok: true });
});

// ---------- API: pedidos ----------
// Registrar pedido (cliente: usa su propio ID; administrador: indica el ID del cliente)
app.post('/api/pedidos', requiereSesion, (req, res) => {
  const s = req.session.usuario;
  const v = validarPedido(req.body);
  if (v.error) return res.status(400).json({ error: v.error });

  let idCliente = s.id;
  if (s.tipo === 'PT') {
    idCliente = txt(req.body.idCliente);
    if (!/^\d{4}$/.test(idCliente)) return res.status(400).json({ error: 'El ID del cliente debe tener 4 dígitos.' });
    if (!leer(F_USUARIOS).some(x => x.id === idCliente)) return res.status(400).json({ error: 'El ID de cliente no existe.' });
  }
  const pedidos = leer(F_PEDIDOS);
  const idPedido = pedidos.reduce((m, p) => Math.max(m, p.idPedido), 0) + 1;
  const nuevo = { idPedido, idCliente, ...v.ok };
  pedidos.push(nuevo);
  guardar(F_PEDIDOS, pedidos);
  res.status(201).json({ pedido: nuevo });
});

// Consultar mis pedidos (del usuario con sesión activa)
app.get('/api/pedidos/mios', requiereSesion, (req, res) => {
  const id = req.session.usuario.id;
  res.json({ idCliente: id, pedidos: leer(F_PEDIDOS).filter(p => p.idCliente === id).sort((a, b) => b.idPedido - a.idPedido) });
});

// Administrar: listar (opcionalmente filtrado por cliente), editar, eliminar
app.get('/api/admin/pedidos', requiereAdmin, (req, res) => {
  const c = txt(req.query.cliente);
  let lista = leer(F_PEDIDOS);
  if (c) lista = lista.filter(p => p.idCliente === c);
  res.json({ pedidos: lista.sort((a, b) => b.idPedido - a.idPedido) });
});

app.put('/api/admin/pedidos/:id', requiereAdmin, (req, res) => {
  const v = validarPedido(req.body);
  if (v.error) return res.status(400).json({ error: v.error });
  const pedidos = leer(F_PEDIDOS);
  const p = pedidos.find(x => x.idPedido === Number(req.params.id));
  if (!p) return res.status(404).json({ error: 'Pedido no encontrado.' });
  const idCliente = txt(req.body.idCliente) || p.idCliente;
  if (!leer(F_USUARIOS).some(x => x.id === idCliente)) return res.status(400).json({ error: 'El ID de cliente no existe.' });
  Object.assign(p, v.ok, { idCliente });
  guardar(F_PEDIDOS, pedidos);
  res.json({ pedido: p });
});

app.delete('/api/admin/pedidos/:id', requiereAdmin, (req, res) => {
  const pedidos = leer(F_PEDIDOS);
  const i = pedidos.findIndex(x => x.idPedido === Number(req.params.id));
  if (i < 0) return res.status(404).json({ error: 'Pedido no encontrado.' });
  pedidos.splice(i, 1);
  guardar(F_PEDIDOS, pedidos);
  res.json({ ok: true });
});

app.listen(PORT, () => console.log(`El Multiverso listo en http://localhost:${PORT}`));
