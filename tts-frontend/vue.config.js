module.exports = {
    // 其他配置（如 devServer、publicPath 等）
    devServer: {
        port: 8080,  // 前端端口，确保与后端 CORS 配置中的源一致
        proxy: {
            '/api': {
                target: 'http://localhost:8000',  // 后端接口地址
                changeOrigin: true,
                pathRewrite: { '^/api': '' }
            }
        }
    },
    configureWebpack: {
        optimization: {
            splitChunks: {
                // 移除直接在 splitChunks 下的 vendor，改为放在 cacheGroups 中
                cacheGroups: {
                    vendor: {  // 这里是正确的位置：在 cacheGroups 内定义 vendor 分块规则
                        chunks: 'all',
                        test: /[\\/]node_modules[\\/]/,  // 匹配 node_modules 中的依赖
                        name: 'vendors',  // 生成的 chunk 名称
                        priority: 10,  // 优先级（数值越大越优先）
                        enforce: true
                    }
                }
            }
        }
    }
}
