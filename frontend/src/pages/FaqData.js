module.exports = {
    'data': [
        {
          key: '1',
          action: 'Visit Link',
          owner: '*',
          editor: '*',
          viewer: '*',
          everyone: '*',
        },
        {
          key: '2',
          action: 'View Link Info',
          owner: '*',
          editor: '*',
          viewer: '*',
          everyone: '',
        },
        {
          key: '3',
          action: 'View Link Stats',
          owner: '*',
          editor: '*',
          viewer: '*',
          everyone: '',
        },
        {
          key: '4',
          action: 'View Link Visits',
          owner: '*',
          editor: '*',
          viewer: '*',
          everyone: '',
        },
        {
          key: '5',
          action: 'View Alias Stats',
          owner: '*',
          editor: '*',
          viewer: '*',
          everyone: '',
        },
        {
          key: '6',
          action: 'View Alias Visits',
          owner: '*',
          editor: '*',
          viewer: '*',
          everyone: '',
        },
        {
          key: '7',
          action: 'Create Alias',
          owner: '*',
          editor: '*',
          viewer: '',
          everyone: '',
        },
        {
          key: '8',
          action: 'Modify Link',
          owner: '*',
          editor: '*',
          viewer: '',
          everyone: '',
        },
        {
          key: '9',
          action: 'Modify Link Permissions',
          owner: '*',
          editor: '*',
          viewer: '',
          everyone: '',
        },
        {
          key: '10',
          action: 'Modify Link Owner',
          owner: '*',
          editor: '',
          viewer: '',
          everyone: '',
        },
        {
          key: '11',
          action: 'Delete Alias',
          owner: '*',
          editor: '',
          viewer: '',
          everyone: '',
        },
        {
          key: '12',
          action: 'Delete Link',
          owner: '*',
          editor: '',
          viewer: '',
          everyone: '',
        },
        {
          key: '13',
          action: 'Reset Visit Count',
          owner: '*',
          editor: '',
          viewer: '',
          everyone: '',
        },
    ],
    'cols': [
        {
            title: 'Action',
            dataIndex: 'action',
            key: 'action',
            align: 'left',
          },
          {
            title: 'Owner',
            dataIndex: 'owner',
            key: 'owner',
            align: 'center',
          },
          {
            title: 'Editor',
            dataIndex: 'editor',
            key: 'editor',
            align: 'center',
          },
          {
            title: 'Viewer',
            dataIndex: 'viewer',
            key: 'viewer',
            align: 'center',
          },
          {
            title: 'Everyone',
            dataIndex: 'everyone',
            key: 'everyone',
            align: 'center',
          },
    ]
};
