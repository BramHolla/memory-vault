"""UI string translations for the gallery and admin pages."""

TRANSLATIONS = {
    'en': {
        # Gallery — filters
        'filter_all':    'All',
        'filter_photos': 'Photos',
        'filter_videos': 'Videos',
        'clear_filters': 'Clear filters',
        'map_toggle':    'Map',
        'sign_out':      'Sign out',
        # Gallery — quick date buttons
        'quick':         'Quick:',
        'today':         'Today',
        'this_week':     'This week',
        'this_month':    'This month',
        'all_years':     'All years',
        # Gallery — empty state
        'no_memories':      'No memories found',
        'no_memories_hint': 'Adjust the filters to see more',
        # Gallery — stats badge  (use .format(total=…, images=…, videos=…))
        'stats_badge': '{total} memories  •  {images} photos  •  {videos} videos',
        # Language toggle
        'lang_switch_label': 'NL',
        # Admin — navigation
        'back_to_gallery': '← Back to gallery',
        # Admin — users table
        'users_count':   'Users',
        'add_user':      '+ Add user',
        'col_id':        'ID',
        'col_email':     'Email',
        'col_memories':  'Memories',
        'col_last_sync': 'Last sync',
        'col_actions':   'Actions',
        'no_users':      'No users found.',
        # Admin — action buttons
        'copy':           'Copy',
        'copied':         'Copied!',
        'new_key':        'New key',
        'reset_password': 'Reset password',
        'delete':         'Delete',
        # Admin — sync instructions section
        'sync_instructions': 'Sync instructions for users',
        # Admin — add user modal
        'add_user_modal_title': 'Add user',
        'admin_privileges':    'Admin privileges',
        'create_send_invite':  'Create & send invite',
        'cancel':              'Cancel',
        'invite_hint': (
            'The user will receive an invitation email with a link to set their password. '
            'Share the API key with them separately for use with the sync tool.'
        ),
    },
    'nl': {
        # Gallery — filters
        'filter_all':    'Alles',
        'filter_photos': "Foto's",
        'filter_videos': "Video's",
        'clear_filters': 'Wis filters',
        'map_toggle':    'Kaart',
        'sign_out':      'Uitloggen',
        # Gallery — quick date buttons
        'quick':         'Snel:',
        'today':         'Vandaag',
        'this_week':     'Deze week',
        'this_month':    'Deze maand',
        'all_years':     'Alle jaren',
        # Gallery — empty state
        'no_memories':      'Geen herinneringen gevonden',
        'no_memories_hint': 'Pas de filters aan om meer te zien',
        # Gallery — stats badge
        'stats_badge': "{total} herinneringen  •  {images} foto's  •  {videos} video's",
        # Language toggle
        'lang_switch_label': 'EN',
        # Admin — navigation
        'back_to_gallery': '← Terug naar gallery',
        # Admin — users table
        'users_count':   'Gebruikers',
        'add_user':      '+ Gebruiker toevoegen',
        'col_id':        'ID',
        'col_email':     'E-mail',
        'col_memories':  'Herinneringen',
        'col_last_sync': 'Laatste sync',
        'col_actions':   'Acties',
        'no_users':      'Geen gebruikers gevonden.',
        # Admin — action buttons
        'copy':           'Kopieer',
        'copied':         'Gekopieerd!',
        'new_key':        'Nieuwe key',
        'reset_password': 'Reset wachtwoord',
        'delete':         'Verwijderen',
        # Admin — sync instructions section
        'sync_instructions': 'Sync-instructies voor gebruikers',
        # Admin — add user modal
        'add_user_modal_title': 'Gebruiker toevoegen',
        'admin_privileges':    'Admin-rechten',
        'create_send_invite':  'Aanmaken & uitnodiging sturen',
        'cancel':              'Annuleren',
        'invite_hint': (
            'De gebruiker ontvangt een uitnodigingsmail met een link om het wachtwoord in te stellen. '
            'Deel de API-key apart met hem/haar voor gebruik met de sync-tool.'
        ),
    },
}
