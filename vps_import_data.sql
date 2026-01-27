-- Quick import of accounts and channels for VPS
-- Generated: 2026-01-27

-- Insert accounts (with encrypted session strings from local DB)
-- Note: Session files are already on VPS in /opt/traffic-engine/sessions/
-- These are placeholder inserts - actual session_strings need to be copied from local DB

-- Check if tenant exists
INSERT INTO traffic_tenants (id, name, display_name, description, funnel_link, is_active, created_at, updated_at)
VALUES (1, 'infobusiness', 'Инфобизнес - Курсы по заработку', 'Привлечение трафика для продажи курсов по онлайн-заработку', 'https://t.me/infobiz_bot?start=traffic', true, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- Note: Run scripts/add_account.py or scripts/load_sessions_from_files.py on VPS to add accounts
-- We cannot copy session_string directly as they may be encrypted

-- Add sample channels (these are safe to copy)
INSERT INTO traffic_target_channels (tenant_id, channel_id, username, title, is_active, priority, comment_strategy, max_delay_minutes, skip_ads, skip_reposts, min_post_length, created_at, updated_at)
VALUES
  (1, 1405730877, 'dindex', 'Дмитрий Индекс', true, 8, 'smart', 5, true, true, 50, NOW(), NOW()),
  (1, 1157637130, 'ventureStuff', 'Заметки по стартапам | Street MBA', true, 7, 'expert', 5, true, true, 50, NOW(), NOW()),
  (1, 1005993407, 'pisarevich', 'Алексей Писаревич', true, 7, 'expert', 5, true, true, 50, NOW(), NOW())
ON CONFLICT (channel_id) DO NOTHING;

-- Check the data
-- SELECT * FROM traffic_userbot_accounts;
-- SELECT * FROM traffic_target_channels WHERE is_active=true;
