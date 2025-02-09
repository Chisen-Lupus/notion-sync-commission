# 数据库的过滤条件. 更改这个变量以适应不同的数据库. 

page_filters = {
    '状态': '完成',
    # '类型': '电绘',
}

# 一个页面由很多的blocks构成, 这里只筛选类型为image的block. 不需要更改这个变量.

block_filters = {
    'type': 'image'
}

# 默认需要数据库中有一个日期tag加进文件名, 所以需要这个tag在数据库中的名称. 如果文件名中不想要日期的话就手动改一下action-webdav.py吧.

date_property = '更新日期'

# 页面标题对应的tag名称. 默认就是Name, 所以如果没有在Notion中更改的话这里也不需要改. 

name_property = 'Name'

# 需要同步的文件夹在WebDAV文件夹中的位置

webdav_outdir = '/SWAP/Commissions/'

# 日志的位置

webdav_logname = 'workflow.log'