-- MySQL 容器第一次启动（数据卷为空）时由 docker-entrypoint-initdb.d 自动执行。
-- 库名需与 .env 里的 MYSQL_DB 一致，默认 nutri_agent。

CREATE DATABASE IF NOT EXISTS nutri_agent
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE nutri_agent;

CREATE TABLE IF NOT EXISTS diet_records (
  id              INT         NOT NULL AUTO_INCREMENT,
  request_data    JSON        NOT NULL COMMENT '用户请求参数快照',
  final_plan      JSON        NULL     COMMENT '最终食谱（含每食材与总计的成本/热量/蛋白）',
  review_feedback TEXT        NULL     COMMENT '审查未通过的原因',
  retry_count     INT         NOT NULL DEFAULT 0,
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
