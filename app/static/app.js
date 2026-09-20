// Entry: hand core the pages, then boot. One file per module, keyed by the module's name.
import { registerPages, boot } from './core.js';
import home from './pages/home.js';
import chat from './pages/chat.js';
import email from './pages/email.js';
import education from './pages/education.js';
import second_brain from './pages/second_brain.js';
import science from './pages/science.js';
import finance from './pages/finance.js';
import newsfeed from './pages/newsfeed.js';
import graph from './pages/graph.js';
import database from './pages/database.js';
import activity from './pages/activity.js';
import settings from './pages/settings.js';

registerPages({ home, chat, email, education, second_brain, science, finance, newsfeed, graph, database, activity, settings });

// The agent drawer and point mode register themselves with core; the shell runs without either.
for (const part of ['./chat.js', './point.js']) {
  try { await import(part); } catch (e) { console.error(`${part} did not load`, e); }
}

boot();
