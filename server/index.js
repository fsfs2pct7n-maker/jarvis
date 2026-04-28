require('dotenv').config();
const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const cors = require('cors');
const path = require('path');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../client')));

const routes = ['chat', 'tasks', 'gmail', 'calendar', 'github', 'messages', 'files', 'memory', 'briefing'];
routes.forEach(route => {
  try { app.use('/api/' + route, require('./routes/' + route)); } catch (e) {}
});

wss.on('connection', (ws) => {
  console.log('WebSocket client connected');
  ws.on('message', (msg) => { ws.send(JSON.stringify({ type: 'echo', msg: msg.toString() })); });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => console.log('Jarvis running on port ' + PORT));