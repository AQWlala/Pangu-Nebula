import { render } from 'preact'
import './styles/variables.css'
import './index.css'
import App from './app'
import { initSidecarListener } from './lib/api'

// v2.1.0 Phase 0: Tauri sidecar 模式下注册事件监听
// PyWebView 模式下为 no-op
initSidecarListener()

render(<App />, document.getElementById('app')!)
