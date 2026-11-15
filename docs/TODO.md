# À faire

La liste des travaux ouverts de **media_library** est désormais tenue dans
[Notion](https://app.notion.com/p/419da06137f2810d8615d4b52580b996?pvs=204).
Ce qui a été tranché est dans [decisions.md](decisions.md).

Ce fichier reste volontairement dans le dépôt comme point d'entrée stable pour
les liens existants. Ne pas y ajouter de tâches : mettre à jour la page Notion
avec le connecteur MCP du projet.

## Connexion MCP

- **Codex** : la configuration partagée est dans `.codex/config.toml`. À la
  première utilisation, lancer `codex mcp login notion`, puis terminer
  l'autorisation OAuth dans le navigateur.
- **Claude Code** : la configuration partagée est dans `.mcp.json`. À la
  première utilisation, approuver le serveur dans `/mcp`, puis terminer
  l'autorisation OAuth.

Aucun jeton Notion n'est stocké dans le dépôt.
