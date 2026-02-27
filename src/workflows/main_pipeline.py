#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-11 22:31:22
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-01-29 01:44:52
# FilePath: \NewsPilot\src\workflows\main_pipeline.py
# Description: NewsPilot 主流程控制器 - 完整的每日新闻分析流水线
# NewsPilot 主流程控制器
# 完整的每日新闻分析流水线
# Copyright (c) 2026 by , All Rights Reserved. 

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.data_acquisition.orchestrator import NewsDataOrchestrator
from src.intelligence.insight_generator import InsightGenerator
from core.news_schemas import NewsItemRefinedSchema, NewsItemRawSchema

# 配置日志
# 先确保日志目录存在
from pathlib import Path
Path('data/logs').mkdir(parents=True, exist_ok=True)


LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

logging.basicConfig(
    level=logging.INFO,  # 你自己的默认级别
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            'data/logs/pipeline.log',
            encoding='utf-8'
        )
    ]
)
# 🔕 关闭第三方 HTTP 噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# （可选）如果你用到了 aiohttp / urllib3
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


class NewsPilotPipeline:
    """
    NewsPilot 主流程控制器
    
    完整流程：
    1. 新闻采集与处理（通过 NewsDataOrchestrator）
    2. 个性化洞察生成（通过 InsightGenerator）
    3. 报告保存
    """
    
    def __init__(
        self,
        news_config: Optional[Dict] = None,
        insight_model: str = "gemini",
        output_dir: str = "data/reports"
    ):
        """
        初始化主流程
        
        Args:
            news_config: 新闻采集配置（传给 NewsDataOrchestrator）
            insight_model: 洞察生成使用的模型
            output_dir: 输出目录
        """
        # 新闻配置（如果未提供则使用默认值）
        self.news_config = news_config or {
            'source': ['newsapi', 'rsshub'],
            'translator_flag': True,
            'summarizer_flag': True,
            'target_language': 'zh',
            'translator_model': 'deepseek',
            'summarizer_model': 'deepseek',
        }
        
        self.insight_model = insight_model
        self.output_dir = Path(output_dir)
        
        # 初始化模块
        self.news_orchestrator = NewsDataOrchestrator(news_config=self.news_config)
        self.insight_generator = InsightGenerator(model_name=self.insight_model)
    
    def run(
        self, 
        save_intermediate: bool = True,
        max_news_for_insight: Optional[int] = None
    ) -> Dict:
        """
        运行完整流程（同步接口）
        
        Args:
            save_intermediate: 是否保存中间结果（精炼新闻）
            max_news_for_insight: 用于洞察生成的最大新闻数（None=全部）
        
        Returns:
            包含所有输出路径和统计信息的字典
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        logger.info("="*70)
        logger.info(f"NewsPilot 主流程开始 - {date_str}")
        logger.info("="*70)
        
        try:
            # ========== Step 1: 新闻采集与处理 ==========
            logger.info("[1/3] 开始新闻采集与处理...")
            logger.info(f"配置 - 新闻源: {self.news_config['source']}")
            logger.info(f"配置 - 翻译: {'启用' if self.news_config['translator_flag'] else '禁用'}")
            logger.info(f"配置 - 摘要: {'启用' if self.news_config['summarizer_flag'] else '禁用'}")
            
            # 调用 orchestrator
            raw_news, pipeline_result = self.news_orchestrator.run()
            
            # 安全检查返回值
            if not isinstance(pipeline_result, dict):
                raise ValueError(f"Pipeline result 格式错误，期望 dict，实际: {type(pipeline_result)}")
            
            translated_items = pipeline_result.get("translated_items")
            summarized_items = pipeline_result.get("summarized_items")
            
            # 验证数据完整性
            if not raw_news:
                logger.warning("未获取到任何原始新闻")
                return self._create_empty_result(date_str)
            
            if not summarized_items and not translated_items:
                logger.error("Pipeline 处理失败，未获得任何输出")
                raise RuntimeError("新闻处理流程未产生任何结果")
            
            # 使用可用的最终结果
            final_news = summarized_items if summarized_items else translated_items
            final_news = sorted(
                final_news,
                key=lambda item: item.evaluation_score if item.evaluation_score is not None else 0,
                reverse=True,
            )
            logger.info(f"新闻处理完成 - 原始: {len(raw_news)}, 最终: {len(final_news)}")
            
            # 保存中间结果
            raw_news_path = None
            translated_items_path = None
            summarized_items_path = None
            
            if save_intermediate:
                try:
                    raw_news_path = self._save_raw_news(raw_news, date_str)
                    logger.info(f"已保存原始新闻至: {raw_news_path}")
                    
                    if translated_items:
                        translated_items_path = self._save_translated_news(translated_items, date_str)
                        logger.info(f"已保存翻译新闻至: {translated_items_path}")
                    
                    if summarized_items:
                        summarized_items_path = self._save_summarized_news(summarized_items, date_str)
                        logger.info(f"已保存摘要新闻至: {summarized_items_path}")
                except Exception as e:
                    logger.error(f"保存中间结果失败: {e}", exc_info=True)
            
            # ========== Step 2: 个性化洞察生成 ==========
            logger.info(f"[2/3] 开始生成个性化洞察...")
            logger.info(f"使用模型: {self.insight_model}")
            
            # 限制用于洞察生成的新闻数量
            

            news_for_insight = (
                final_news[:max_news_for_insight] 
                if max_news_for_insight 
                else final_news
            )
            logger.info(f"将分析 {len(news_for_insight)} 条新闻")
            
            try:
                insights = self.insight_generator.generate_insights(
                    news_items=news_for_insight,
                    user_profile=None  # 当前从文件加载
                )
                
                if not insights or not insights.get('insights'):
                    logger.warning("洞察生成返回空结果")
                    insights = {'insights': '洞察生成失败', 'user_id': 'unknown', 'date': date_str}
                
                logger.info("洞察生成完成")
            except Exception as e:
                logger.error(f"洞察生成失败: {e}", exc_info=True)
                insights = {
                    'insights': f'洞察生成时出错: {str(e)}',
                    'user_id': 'error',
                    'date': date_str
                }
            
            # ========== Step 3: 保存结果 ==========
            logger.info("[3/3] 保存分析结果...")
            
            try:
                insights_path = self._save_insights(insights, date_str)
                logger.info(f"洞察报告已保存: {insights_path}")
                
                report_path = self._generate_summary_report(
                    refined_news=final_news,
                    insights=insights,
                    date_str=date_str
                )
                logger.info(f"汇总报告已保存: {report_path}")
            except Exception as e:
                logger.error(f"保存报告失败: {e}", exc_info=True)
                raise
            
            # ========== 完成 ==========
            logger.info("="*70)
            logger.info("流程完成！")
            logger.info("="*70)
            
            return {
                "date": date_str,
                "raw_news_path": str(raw_news_path) if raw_news_path else None,
                "translated_items_path": str(translated_items_path) if translated_items_path else None,
                "summarized_items_path": str(summarized_items_path) if summarized_items_path else None,
                "insights_path": str(insights_path),
                "report_path": str(report_path),
                "total_news_count": len(final_news),
                "analyzed_news_count": len(news_for_insight),
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"主流程执行失败: {e}", exc_info=True)
            return {
                "date": date_str,
                "status": "failed",
                "error": str(e),
                "total_news_count": 0
            }
    
    def _create_empty_result(self, date_str: str) -> Dict:
        """创建空结果（当没有新闻时）"""
        logger.warning("创建空结果")
        return {
            "date": date_str,
            "status": "empty",
            "total_news_count": 0,
            "message": "未获取到任何新闻"
        }
    
    def _save_summarized_news(
        self, 
        news_items: List[NewsItemRefinedSchema], 
        date_str: str
    ) -> Path:
        """保存精炼后的新闻"""
        try:
            output_dir = self.output_dir / date_str
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / "summarized_news.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    [item.dict() for item in news_items],
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str
                )
            logger.debug(f"已保存摘要新闻: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"保存摘要新闻失败: {e}", exc_info=True)
            raise
    def _save_translated_news(
        self,
        news_items: List[NewsItemRefinedSchema], 
        date_str: str
    ) -> Path:
        """保存翻译后的新闻"""
        try:
            output_dir = self.output_dir / date_str
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / "translated_news.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    [item.dict() for item in news_items],
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str
                )
            logger.debug(f"已保存翻译新闻: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"保存翻译新闻失败: {e}", exc_info=True)
            raise
    
    def _save_raw_news(
        self,
        news_items: List[NewsItemRawSchema],
        date_str: str
    ) -> Path:
        """保存原始新闻"""
        try:
            output_dir = self.output_dir / date_str
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / "raw_news.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    [item.dict() for item in news_items],
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str
                )
            logger.debug(f"已保存原始新闻: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"保存原始新闻失败: {e}", exc_info=True)
            raise

        
    
    def _save_insights(self, insights: Dict, date_str: str) -> Path:
        """保存洞察结果"""
        try:
            output_dir = self.output_dir / date_str
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / "personalized_insights.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(insights, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存洞察结果: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"保存洞察结果失败: {e}", exc_info=True)
            raise
    
    def _generate_summary_report(
        self, 
        refined_news: List[NewsItemRefinedSchema],
        insights: Dict,
        date_str: str
    ) -> Path:
        """生成 Markdown 汇总报告"""
        try:
            output_dir = self.output_dir / date_str
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 安全获取洞察内容
            insights_text = insights.get('insights', '无洞察内容')
            
            # 构建 Markdown 内容
            md_content = f"""# 📰 NewsPilot 每日报告

**日期：** {date_str}  
**生成时间：** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**分析新闻数：** {len(refined_news)} 条

---

## 💡 个性化洞察

{insights_text}

---

## 📋 新闻列表

"""
            # 添加新闻列表
            for i, item in enumerate(refined_news, 1):
                published_time = item.published_at.strftime("%Y-%m-%d %H:%M") if item.published_at else "未知"
                abstract_text = item.abstract[:300] if item.abstract else '无'
                
                md_content += f"""### {i}. {item.title}

- **来源：** {item.source_channel}
- **时间：** {published_time}
- **链接：** {item.source_url}
- **摘要：** {abstract_text}...

"""
            
            md_content += f"""---

*本报告由 NewsPilot 自动生成*
"""
            
            output_path = output_dir / "daily_report.md"
            output_path.write_text(md_content, encoding="utf-8")
            logger.debug(f"已生成汇总报告: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"生成汇总报告失败: {e}", exc_info=True)
            raise


# ==================== 主入口 ====================
def main():
    """主入口函数"""
    try:
        logger.info("NewsPilot 主程序启动")
        
        # 配置（可以从命令行参数或配置文件读取）
        news_config = {
            'source': ['newsapi', 'rsshub'],
            'translator_flag': True,
            'summarizer_flag': True,
            'target_language': 'zh',
            'translator_model': 'deepseek',
            'summarizer_model': 'deepseek',
        }
        
        # 创建并运行主流程
        pipeline = NewsPilotPipeline(
            news_config=news_config,
            insight_model="gemini",
            output_dir="data/reports"
        )
        
        result = pipeline.run(
            save_intermediate=True,
            max_news_for_insight=None
        )
        
        # 打印结果摘要
        logger.info("执行完成")
        logger.info(f"状态: {result.get('status', 'unknown')}")
        if result.get('status') == 'success':
            logger.info(f"分析新闻数: {result.get('total_news_count', 0)}")
            logger.info(f"报告路径: {result.get('report_path', 'N/A')}")
        else:
            logger.error(f"错误信息: {result.get('error', 'N/A')}")
        
        return result
        
    except Exception as e:
        logger.critical(f"主程序异常退出: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
