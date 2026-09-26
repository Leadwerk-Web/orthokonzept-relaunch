<?php
/**
 * Kontaktformular orthoKonzept: nimmt POST vom Formular unter /kontakt/ an und versendet per mail().
 * Antwortet mit JSON. Ohne funktionierenden Mailversand liefert es ok:false, das Formular
 * öffnet dann das E-Mail-Programm des Besuchers (Fallback in main.js).
 * Vor dem Livegang: Empfänger prüfen, SPF/DKIM der Absenderdomain beim Hoster klären.
 */
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('X-Robots-Tag: noindex');

const EMPFAENGER = 'info@orthokonzept.de';
const ABSENDER = 'website@orthokonzept.de';

function antwort(bool $ok, string $fehler = '', int $code = 200): void {
    http_response_code($code);
    echo json_encode(['ok' => $ok, 'error' => $fehler], JSON_UNESCAPED_UNICODE);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    antwort(false, 'Nur POST', 405);
}
// Honeypot: echte Besucher lassen das Feld leer
if (!empty($_POST['website'])) {
    antwort(true);
}
$feld = static fn(string $k, int $max) => trim(mb_substr(str_replace(["\r", "\0"], '', (string)($_POST[$k] ?? '')), 0, $max));
$name = $feld('name', 120);
$mail = $feld('email', 160);
$tel = $feld('telefon', 60);
$betreff = $feld('betreff', 160);
$text = $feld('nachricht', 3000);
$ds = !empty($_POST['datenschutz']);

if ($name === '' || $betreff === '' || $text === '' || !$ds || !filter_var($mail, FILTER_VALIDATE_EMAIL)) {
    antwort(false, 'Pflichtfelder fehlen', 422);
}
// einfache Drosselung je IP (1 Nachricht pro 30 Sekunden)
$tmp = sys_get_temp_dir() . '/ok-form-' . md5($_SERVER['REMOTE_ADDR'] ?? 'x');
if (is_file($tmp) && time() - (int)filemtime($tmp) < 30) {
    antwort(false, 'Bitte kurz warten', 429);
}
@touch($tmp);

$zeilen = [
    "Neue Anfrage über www.orthokonzept.de/kontakt/",
    "",
    "Name:    $name",
    "E-Mail:  $mail",
    "Telefon: " . ($tel !== '' ? $tel : '-'),
    "Betreff: $betreff",
    "",
    $text,
    "",
    "Datenschutzhinweis bestätigt: ja",
    "Gesendet: " . date('d.m.Y H:i'),
];
$kopf = [
    'From: orthoKonzept Website <' . ABSENDER . '>',
    'Reply-To: ' . str_replace(["\n", "\r"], '', $name) . ' <' . $mail . '>',
    'Content-Type: text/plain; charset=UTF-8',
    'MIME-Version: 1.0',
];
$subject = '=?UTF-8?B?' . base64_encode('Kontaktanfrage: ' . $betreff) . '?=';
$ok = @mail(EMPFAENGER, $subject, implode("\n", $zeilen), implode("\r\n", $kopf), '-f' . ABSENDER);
$ok ? antwort(true) : antwort(false, 'Versand fehlgeschlagen', 500);
