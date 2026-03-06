import pandas as pd


def query_excel_data(file_path, search_keyword):
    try:
        # 1. 读取 Excel 文件
        # header=0 表示第一行是表头
        df = pd.read_excel(file_path, header=0)

        # 2. 关键步骤：处理合并单元格
        # pandas读取合并单元格时，只有第一行有值，下面是NaN。
        # ffill() 会把上面的值填充到下面空的单元格中。
        df['监测入楼ODF成端位置'] = df['监测入楼ODF成端位置'].ffill()

        # 3. 也可以处理一下右侧的合并单元格（如果检测端口也是合并的）
        # df['检测端口'] = df['检测端口'].ffill()

        # 4. 填充剩余的空值为特定字符串，防止报错
        df = df.fillna("无")

        # 5. 过滤数据
        # 筛选 '监测入楼ODF成端位置' 列包含搜索关键词的行
        result = df[df['监测入楼ODF成端位置'].str.contains(search_keyword, na=False)]

        if result.empty:
            print(f"未找到包含 '{search_keyword}' 的记录。")
            return

        # 6. 打印结果
        # 获取去重后的位置名称，因为可能对应多行
        locations = result['监测入楼ODF成端位置'].unique()

        for loc in locations:
            print(f"\n====== 位置: {loc} ======")
            subset = result[result['监测入楼ODF成端位置'] == loc]

            # 遍历打印该位置下的所有点位和端口
            for index, row in subset.iterrows():
                desc = row['点位描述']
                port = row['检测端口']
                print(f"  - 描述: {desc} \t| 端口: {port}")

    except FileNotFoundError:
        print("错误：找不到指定的 Excel 文件，请检查路径。")
    except Exception as e:
        print(f"发生错误: {e}")

# --- 使用说明 ---
# 假设您的文件名为 'data.xlsx'
query_excel_data('/Users/collin/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_9723377223912_f548/msg/file/2025-11/FMS点位表.xlsx', '德信6层03区域B03#')