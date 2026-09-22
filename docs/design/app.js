// Entry: the parts register themselves with core as they load, then the shell boots.
import { boot } from './shell.js';
import './brain.js';
import './drawer.js';
import './point.js';

boot();
