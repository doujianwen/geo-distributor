<?php
/** Isolated acceptance: separate WP table, no email, loopback test API only. */
define('DISABLE_WP_CRON', true);
require 'E:/xampp/htdocs/geo-growth-site/wp-load.php';
global $wpdb;
$source = ggs_leads_table_name();
$wpdb->prefix = 'portal_acc_' . gmdate('YmdHis') . '_';
$table = ggs_leads_table_name();
if (!preg_match('/^[a-zA-Z0-9_]+$/', $table)) { throw new Exception('Invalid acceptance table'); }
$wpdb->query("CREATE TABLE `$table` LIKE `$source`");
add_filter('ggs_leads_intake_endpoint', function () { return 'http://127.0.0.1:8766/leads'; });
$values = array('name'=>'Portal Acceptance','company'=>'Isolated Acceptance','email'=>'acceptance@example.test','domain'=>'example.test','type'=>'diagnostic','message'=>'Isolated acceptance; no external notification.');
$old = ggs_leads_store($values, array('source'=>'portal-acc-' . gmdate('His')));
$new = ggs_leads_store($values, array('source'=>'portal-acc-' . gmdate('His')));
if (!$old || !$new) { throw new Exception('Acceptance table persistence failed'); }
add_filter('pre_option_ggs_leads_auto_retry_min_id', function () use ($new) { return $new; });
ggs_leads_retry_pending();
$rows = $wpdb->get_results("SELECT id,intake_status,intake_attempts,intake_remote_id FROM `$table` ORDER BY id", ARRAY_A);
if ((int)$rows[0]['intake_attempts'] !== 0 || (int)$rows[1]['intake_attempts'] !== 1 || empty($rows[1]['intake_remote_id'])) {
    throw new Exception('Historical retry protection or new intake acceptance failed');
}
echo json_encode(array('status'=>'PASS','table'=>$table,'old_backlog_untouched'=>true,'new_intake_persisted'=>true,'rows'=>$rows), JSON_UNESCAPED_UNICODE);
