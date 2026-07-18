// Shiori desktop — fenêtre native autour de l'app HTML (aucune logique ici :
// tout le convertisseur vit dans le HTML, identique au site).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("erreur au lancement de Shiori");
}
