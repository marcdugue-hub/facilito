"""Agent tool schemas for OpenAI/DeepSeek function-calling."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_facilitators",
            "description": "Liste tous les facilitateurs existants avec leur identifiant. Utiliser pour trouver l'ID d'un facilitateur par son nom.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_sessions",
            "description": "Liste toutes les sessions avec leur date, statut et facilitateur. Utilise CET outil quand l'utilisateur demande de lister des sessions, consulter un calendrier, voir les sessions à venir, ou filtrer par date/période. Les résultats contiennent les dates — tu peux ensuite les filtrer toi-même par période.",
            "parameters": {
                "type": "object",
                "properties": {
                    "facilitator_id": {"type": "integer", "description": "Filtrer par ID du facilitateur (optionnel)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_practices",
            "description": "RECHERCHE OBLIGATOIRE dans la base RAG pour trouver des pratiques de facilitation. À appeler AVANT add_practice pour voir les pratiques disponibles. Fournir un query décrivant le type de pratique recherché (ex: 'icebreaker', 'idéation', 'rétrospective').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Mots-clés ou description du type de pratique recherché (ex: 'icebreaker', 'brainstorming', 'rétro', 'énergizer')."},
                    "n_results": {"type": "integer", "description": "Nombre de résultats souhaités (défaut 5).", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_context",
            "description": "Lit l'état complet de la session en cours : participants, pratiques, durée totale.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_session",
            "description": "Crée une nouvelle session pour un facilitateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "facilitator_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "Format ISO YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "Heure de début au format HH:MM (ex: 14:00)"},
                    "objective": {"type": "string"},
                },
                "required": ["facilitator_id", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_session",
            "description": "Modifie le titre, la date, l'objectif ou le statut d'une session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "objective": {"type": "string"},
                    "status": {"type": "string", "enum": ["draft", "confirmed", "finished"]},
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_practice",
            "description": "Ajoute une pratique au déroulé de la session. Utilise practice_id retourné par search_practices (RAG) ou SPECIAL_*. Ne pas inventer de titre — utiliser le titre exact retourné par search_practices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "practice_id": {"type": "string", "description": "ID de la pratique (ex: '12') ou 'SPECIAL_PAUSE'."},
                    "titre": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "source": {"type": "string", "enum": ["rag", "special"], "default": "rag"},
                },
                "required": ["session_id", "practice_id", "titre", "duration_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_practice",
            "description": "Retire une pratique du déroulé de la session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "practice_row_id": {"type": "integer", "description": "ID de la ligne session_practices."},
                },
                "required": ["session_id", "practice_row_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_practice",
            "description": "Déplace une pratique vers le haut ou le bas dans le déroulé.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "practice_row_id": {"type": "integer"},
                    "direction": {"type": "string", "enum": ["up", "down"]},
                },
                "required": ["session_id", "practice_row_id", "direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_practice_duration",
            "description": "Modifie la durée d'une pratique dans le déroulé.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "practice_row_id": {"type": "integer"},
                    "duration_minutes": {"type": "integer"},
                },
                "required": ["session_id", "practice_row_id", "duration_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_participant",
            "description": "Crée un nouveau participant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string"},
                },
                "required": ["first_name", "last_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_participant_to_session",
            "description": "Ajoute un participant existant à la session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "participant_id": {"type": "integer"},
                },
                "required": ["session_id", "participant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_team_to_session",
            "description": "Importe tous les membres d'une équipe dans la session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "integer"},
                    "team_id": {"type": "integer"},
                },
                "required": ["session_id", "team_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_client",
            "description": "Crée un nouveau client (organisation, entreprise).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom du client."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_team",
            "description": "Crée une nouvelle équipe, optionnellement rattachée à un client.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom de l'équipe."},
                    "client_id": {"type": "integer", "description": "ID du client auquel rattacher l'équipe (optionnel)."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_clients",
            "description": "Liste tous les clients existants avec leur identifiant.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_teams",
            "description": "Liste toutes les équipes existantes, optionnellement filtrées par client.",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "integer", "description": "Filtrer par client (optionnel)."},
                },
                "required": [],
            },
        },
    },
]

SESSION_SCOPED = {
    "get_session_context", "update_session",
    "add_practice", "remove_practice", "reorder_practice", "update_practice_duration",
    "add_participant_to_session", "add_team_to_session",
}
