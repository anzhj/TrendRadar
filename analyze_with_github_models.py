# coding=utf-8
"""
使用 GitHub Models 的热点趋势分析脚本
简化版本，专注于 AI 增强的关键词分析和投资建议
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import requests

# 导入基础分析功能
from analyze_trends import (
    load_config,
    get_beijing_time,
    analyze_trends,
    send_analysis_report
)


def call_ai_api(prompt: str, context: str = "") -> Optional[str]:
    """
    调用 AI API（支持多种服务）
    优先级: GitHub Models > OpenAI > 其他
    """
    try:
        # 检查配置的 AI 服务
        github_token = os.environ.get("GITHUB_TOKEN", "")
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        model_name = os.environ.get("AI_MODEL", "gpt-4o")
        
        # 构建消息
        messages = [
            {
                "role": "system",
                "content": "你是一位专业的投资分析师和市场趋势专家，擅长从热点新闻中发现投资机会。"
            },
            {
                "role": "user",
                "content": f"{prompt}\n\n数据:\n{context}"
            }
        ]
        
        # 尝试 GitHub Models
        if github_token:
            try:
                print(f"正在调用 GitHub Models ({model_name})...")
                # GitHub Models API 端点（官方文档）
                # 文档: https://docs.github.com/zh/github-models/quickstart
                api_url = "https://models.github.ai/inference/chat/completions"
                
                # 模型名称需要加上提供商前缀
                full_model_name = f"openai/{model_name}" if not model_name.startswith("openai/") else model_name
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {github_token}"
                }
                
                payload = {
                    "messages": messages,
                    "model": full_model_name,
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "top_p": 1.0
                }
                
                response = requests.post(api_url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    ai_response = result["choices"][0]["message"]["content"]
                    print("✓ AI 分析完成 (GitHub Models)")
                    return ai_response
                else:
                    print(f"⚠️  GitHub Models 不可用 (状态码: {response.status_code})")
                    if response.status_code == 401:
                        print(f"   提示: 需要访问 https://github.com/marketplace/models 启用 GitHub Models")
                        print(f"   或配置 OPENAI_API_KEY 作为备选方案")
                    else:
                        print(f"   错误: {response.text[:200]}")
            except Exception as e:
                print(f"⚠️  GitHub Models 失败: {e}")
        
        # 尝试 OpenAI
        if openai_key:
            try:
                print(f"正在调用 OpenAI API ({model_name})...")
                api_url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_key}"
                }
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
                
                response = requests.post(api_url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    ai_response = result["choices"][0]["message"]["content"]
                    print("✓ AI 分析完成 (OpenAI)")
                    return ai_response
                else:
                    print(f"⚠️  OpenAI 调用失败: {response.status_code}")
            except Exception as e:
                print(f"⚠️  OpenAI 失败: {e}")
        
        print("✗ 所有 AI 服务均不可用")
        return None
            
    except Exception as e:
        print(f"✗ AI 调用失败: {e}")
        return None


def prepare_analysis_context(analysis: Dict) -> str:
    """准备分析上下文"""
    context_parts = []
    
    # 新出现的热点
    if analysis.get("new_topics"):
        context_parts.append("【新出现热点】")
        for i, item in enumerate(analysis["new_topics"][:5], 1):
            context_parts.append(f"{i}. {item['keyword']} (出现{item['recent_count']}次, 排名{item.get('avg_rank', 0):.0f})")
            if item["titles"]:
                title = item['titles'][0]['title'][:100]
                url = item['titles'][0].get('url', '') or item['titles'][0].get('mobileUrl', '')
                context_parts.append(f"   新闻: {title}")
                if url:
                    context_parts.append(f"   链接: {url}")
    
    # 上升趋势
    if analysis.get("trending_up"):
        context_parts.append("\n【快速上升热点】")
        for i, item in enumerate(analysis["trending_up"][:5], 1):
            change_pct = item["change_rate"] * 100
            context_parts.append(f"{i}. {item['keyword']} (热度↑{change_pct:.0f}%, 最近{item['recent_count']}次)")
            if item["titles"]:
                title = item['titles'][0]['title'][:100]
                url = item['titles'][0].get('url', '') or item['titles'][0].get('mobileUrl', '')
                context_parts.append(f"   新闻: {title}")
                if url:
                    context_parts.append(f"   链接: {url}")
    
    # 持续热点
    if analysis.get("hot_topics"):
        context_parts.append("\n【持续热点】")
        for i, item in enumerate(analysis["hot_topics"][:5], 1):
            context_parts.append(f"{i}. {item['keyword']} (总计{item['total_count']}次, 排名{item.get('avg_rank', 0):.0f})")
            if item.get("titles"):
                title = item['titles'][0]['title'][:100]
                context_parts.append(f"   新闻: {title}")
    
    # 降温话题
    if analysis.get("trending_down"):
        context_parts.append("\n【降温话题】")
        for i, item in enumerate(analysis["trending_down"][:3], 1):
            change_pct = abs(item["change_rate"]) * 100
            context_parts.append(f"{i}. {item['keyword']} (热度↓{change_pct:.0f}%)")
    
    return "\n".join(context_parts)


def generate_ai_report(analysis: Dict) -> str:
    """生成 AI 增强的分析报告"""
    
    # 准备上下文
    context = prepare_analysis_context(analysis)
    
    # 构建提示词（针对 gpt-4o 优化）
    prompt = f"""
你是一位资深的投资分析师，擅长从热点新闻中发现投资机会。请基于以下热点趋势数据，提供深度的投资分析。

【分析时间】{analysis['analysis_date']}
【数据范围】{analysis['date_range']}

请按以下结构提供分析（每部分3-5条要点，语言简洁专业）：

**1. 核心洞察**
- 分析这些热点背后的深层逻辑和市场趋势
- 识别关键的驱动因素和转折点
- 评估对不同行业的影响程度
- 可以引用具体新闻链接作为依据

**2. 投资机会**
- 具体的投资方向和细分领域
- 推荐关注的行业板块或概念
- 说明投资逻辑和预期收益
- 如果相关，引用新闻链接支持观点

**3. 风险提示**
- 识别主要风险点和不确定性
- 评估风险发生的概率和影响
- 提供风险规避建议

**4. 操作建议**
短期（1周内）：
- 具体的操作方向和时机
- 建议的仓位配置

中期（1-3个月）：
- 战略布局方向
- 关注的催化剂事件

格式要求：
- 建议必须具体可操作，避免泛泛而谈
- 突出最重要的2-3个投资方向
- 用数据和逻辑支撑观点
- 语言专业但易懂
- 引用新闻时使用 Markdown 格式：[新闻标题](链接)
- 这样在飞书等平台中可以直接点击查看
"""
    
    # 调用 AI
    ai_insights = call_ai_api(prompt, context)
    
    # 生成报告
    report = []
    report.append("=" * 60)
    report.append("📊 AI 增强热点趋势分析报告")
    report.append("=" * 60)
    report.append(f"分析时间: {analysis['analysis_date']}")
    report.append(f"数据范围: {analysis['date_range']}")
    report.append(f"关键词总数: {analysis['total_keywords']}")
    report.append("")
    
    # 数据概览
    report.append("📈 **数据概览**")
    report.append(f"- 新出现热点: {len(analysis.get('new_topics', []))} 个")
    report.append(f"- 快速上升热点: {len(analysis.get('trending_up', []))} 个")
    report.append(f"- 持续热点: {len(analysis.get('hot_topics', []))} 个")
    report.append(f"- 降温话题: {len(analysis.get('trending_down', []))} 个")
    report.append("")
    
    # 关键热点（精简版，带超链接）
    if analysis.get("new_topics"):
        report.append("🆕 **新出现热点 TOP3**")
        for i, item in enumerate(analysis["new_topics"][:3], 1):
            keyword = item['keyword']
            count = item['recent_count']
            
            # 获取第一条新闻的链接
            url = ""
            if item.get("titles") and len(item["titles"]) > 0:
                first_title = item["titles"][0]
                url = first_title.get("url", "") or first_title.get("mobileUrl", "")
            
            if url:
                # 飞书格式的超链接
                report.append(f"{i}. [{keyword}]({url}) (出现{count}次)")
            else:
                report.append(f"{i}. {keyword} (出现{count}次)")
        report.append("")
    
    if analysis.get("trending_up"):
        report.append("📈 **快速上升热点 TOP3**")
        for i, item in enumerate(analysis["trending_up"][:3], 1):
            keyword = item['keyword']
            change_pct = item["change_rate"] * 100
            
            # 获取第一条新闻的链接
            url = ""
            if item.get("titles") and len(item["titles"]) > 0:
                first_title = item["titles"][0]
                url = first_title.get("url", "") or first_title.get("mobileUrl", "")
            
            if url:
                # 飞书格式的超链接
                report.append(f"{i}. [{keyword}]({url}) (热度↑{change_pct:.0f}%)")
            else:
                report.append(f"{i}. {keyword} (热度↑{change_pct:.0f}%)")
        report.append("")
    
    # AI 分析结果
    if ai_insights:
        report.append("=" * 60)
        report.append("🤖 **AI 深度分析**")
        report.append("=" * 60)
        report.append(ai_insights)
        report.append("")
    else:
        # 基础建议（如果 AI 不可用）
        report.append("=" * 60)
        report.append("💡 **投资建议**")
        report.append("=" * 60)
        
        if analysis.get("new_topics"):
            top_new = analysis["new_topics"][0]["keyword"]
            report.append(f"🎯 新机会: {top_new} 等新话题突然出现")
        
        if analysis.get("trending_up"):
            top_trending = analysis["trending_up"][0]["keyword"]
            report.append(f"📈 上升机会: {top_trending} 等话题热度快速上升")
        
        if analysis.get("hot_topics"):
            hot_keywords = ", ".join([item['keyword'] for item in analysis['hot_topics'][:3]])
            report.append(f"🔥 稳定配置: {hot_keywords} 等持续热门")
        
        report.append("")
    
    report.append("=" * 60)
    
    return "\n".join(report)


def main():
    """主函数"""
    print("=" * 60)
    print("GitHub Models AI 热点趋势分析")
    print("=" * 60)
    print()
    
    # 检查配置
    if os.environ.get("GITHUB_TOKEN"):
        model = os.environ.get("GITHUB_MODEL", "gpt-4o-mini")
        print(f"✓ GitHub Models 已配置 (模型: {model})")
    else:
        print("⚠️  未配置 GITHUB_TOKEN")
        print("提示: 在 GitHub Secrets 中设置 GITHUB_TOKEN")
    
    print()
    
    # 执行基础分析
    print("步骤 1/3: 执行基础趋势分析...")
    analysis = analyze_trends(days=3)
    
    if "error" in analysis:
        print(f"错误: {analysis['error']}")
        return
    
    print(f"✓ 发现 {analysis['total_keywords']} 个关键词")
    print()
    
    # 生成 AI 报告
    print("步骤 2/3: 生成 AI 增强报告...")
    report = generate_ai_report(analysis)
    print()
    
    # 打印报告
    print(report)
    
    # 保存报告
    print("\n步骤 3/3: 保存报告...")
    beijing_time = get_beijing_time()
    date_folder = beijing_time.strftime("%Y年%m月%d日")
    output_dir = Path("output") / date_folder / "trends"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = output_dir / f"ai_analysis_{beijing_time.strftime('%H%M')}.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"✓ 报告已保存到: {report_file}")
    
    # 发送通知
    if os.environ.get("ENABLE_NOTIFICATION", "true").lower() in ("true", "1"):
        print("\n正在发送通知...")
        send_analysis_report(report)
    
    print("\n✅ 分析完成！")


if __name__ == "__main__":
    main()
