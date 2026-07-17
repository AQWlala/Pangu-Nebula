// 统一日志封装 (v2.3.1)
//
// 替代裸 console.* 调用, debug 级别仅在开发环境输出,
// 生产环境仅保留 warn/error, 避免污染控制台与影响性能。
//
// 用法:
//   import { logger } from '../lib/logger'
//   logger.debug('debug 信息')   // 仅 DEV 输出
//   logger.info('普通信息')
//   logger.warn('警告')
//   logger.error('错误')

const isDev = typeof import.meta !== 'undefined'
  && (import.meta as any).env
  && (import.meta as any).env.DEV

type LogArgs = unknown[]

export const logger = {
  /** 调试日志, 仅在开发环境 (import.meta.env.DEV) 输出 */
  debug: (...args: LogArgs): void => {
    if (isDev) {
      // eslint-disable-next-line no-console
      console.log(...args)
    }
  },
  /** 普通信息日志, 仅在开发环境输出 */
  info: (...args: LogArgs): void => {
    if (isDev) {
      // eslint-disable-next-line no-console
      console.log(...args)
    }
  },
  /** 警告日志, 始终输出 */
  warn: (...args: LogArgs): void => {
    // eslint-disable-next-line no-console
    console.warn(...args)
  },
  /** 错误日志, 始终输出 */
  error: (...args: LogArgs): void => {
    // eslint-disable-next-line no-console
    console.error(...args)
  },
}
