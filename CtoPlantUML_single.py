import os
import glob
import re
import sys


def fetch_c_file_paths(target_dir):
    search_pattern = os.path.join(target_dir, "**", "*.c")
    c_files = glob.glob(search_pattern, recursive=True)
    return c_files


def remove_comments(source_code):
    # ブロックコメント (/* ... */) の除去
    code_without_block = re.sub(r'/\*.*?\*/', '', source_code, flags=re.DOTALL)
    # 行コメント (// ...) の除去
    clean_code = re.sub(r'//.*', '', code_without_block)
    return clean_code

def find_function_definitions(clean_code):
    function_definitions = []
    
    # 戻り値の型、関数名、引数リストのパターンを定義
    # 関数内部の制御構文（for, if等）への誤反応を防ぐため、ネスト解析と併用する
    pattern = re.compile(r'([\w\s\*]+?)\s+(\w+)\s*\((.*?)\)\s*')
    
    idx = 0
    length = len(clean_code)
    
    while idx < length:
        # C言語のトップレベル（中括弧の外側、ネスト深さ0）でのみ関数定義を探索する
        match = pattern.match(clean_code, idx)
        if match:
            # マッチした直後に中括弧 '{' が始まるか、空白・改行を挟んで始まるかを確認
            after_match_idx = match.end()
            # 空白や改行をスキップ
            while after_match_idx < length and clean_code[after_match_idx].isspace():
                after_match_idx += 1
                
            if after_match_idx < length and clean_code[after_match_idx] == '{':
                func_name = match.group(2)
                start_brace_idx = after_match_idx
                
                # 中括弧のペアをカウントして関数の実体ブロックの終端範囲を特定
                brace_count = 0
                scan_idx = start_brace_idx
                
                while scan_idx < length:
                    char = clean_code[scan_idx]
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            break
                    scan_idx += 1
                
                # 開始中括弧から終了中括弧までの関数内部の文字列を切り出す
                func_body = clean_code[start_brace_idx:scan_idx + 1]
                function_definitions.append((func_name, func_body))
                
                # インデックスを関数の終端まで進める
                idx = scan_idx + 1
                continue
                
        idx += 1
        
    return function_definitions


def find_control_block_end(body_content, start_idx):
    """
    制御構文ブロック全体の終了位置をインデックスとして特定する関数。
    開始中括弧が存在しない単一ステートメントの場合は、
    最初に現れるセミコロンの位置を正確な終端として返却する。
    """
    idx = start_idx
    length = len(body_content)
    
    # 制御構文のキーワード部分（for, if, else 等）をスキップ
    while idx < length and body_content[idx].isalpha():
        idx += 1
        
    # キーワードの直後に if が続くケース（else if構文など）への対応
    while idx < length:
        while idx < length and body_content[idx].isspace():
            idx += 1
        if idx < length and body_content.startswith("if", idx):
            idx += 2
        else:
            break
            
    # 空白をスキップして、丸括弧または直接中括弧が始まるかを確認
    while idx < length and body_content[idx].isspace():
        idx += 1
        
    # 条件式の丸括弧がある場合はそのペアをスキップ
    if idx < length and body_content[idx] == '(':
        paren_count = 0
        while idx < length:
            if body_content[idx] == '(':
                paren_count += 1
            elif body_content[idx] == ')':
                paren_count -= 1
                if paren_count == 0:
                    idx += 1
                    break
            idx += 1
            
    # 開始中括弧 '{' までの空白をスキップ
    while idx < length and body_content[idx].isspace():
        idx += 1
        
    # 境界条件：開始中括弧が存在する場合（通常のブロック記述）
    if idx < length and body_content[idx] == '{':
        brace_count = 0
        while idx < length:
            if body_content[idx] == '{':
                brace_count += 1
            elif body_content[idx] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return idx
            idx += 1
        return length - 1
        
    # 境界条件：開始中括弧が存在しない場合（中括弧のない単一ステートメント）
    # 最初に現れるセミコロン ';' の位置を、この制御ブロックの正確な終端インデックスとして返却する
    while idx < length:
        if body_content[idx] == ';':
            return idx
        idx += 1
        
    return length - 1



def classify_statement_type(statement_str):
    """
    切り出されたステートメント文字列のC言語としての構文特徴を解析し、
    typeとcontentを持つ辞書オブジェクトを返却する補助関数。
    """
    # 1. ラベル文の判定
    if statement_str.endswith(':'):
        return {
            "type": "label",
            "content": statement_str
        }

    # 2. リターン文の判定
    if statement_str.startswith("return") and (len(statement_str) == 6 or statement_str[6].isspace() or statement_str[6] == ';'):
        return {
            "type": "return",
            "content": statement_str
        }
        
    # 3. ループ制御切断・継続文の判定
    if statement_str.startswith("break") and (len(statement_str) == 5 or statement_str[5].isspace() or statement_str[5] == ';'):
        return {
            "type": "loop_end",
            "content": statement_str
        }
    if statement_str.startswith("continue") and (len(statement_str) == 8 or statement_str[8].isspace() or statement_str[8] == ';'):
        return {
            "type": "loop_end",
            "content": statement_str
        }
        
    # 4. 関数呼び出しの判定
    # 制御構文のキーワード等を除外し、代入文の右辺にあるケースも含めて丸括弧を伴う関数呼び出しを検知
    if "(" in statement_str:
        match = re.search(r'\b(?!(?:return|break|continue|if|for|while|switch|else)\b)\w+\s*\(', statement_str)
        if match:
            return {
                "type": "function_call",
                "content": statement_str
            }
            
    # 5. 上記のいずれにも該当しない場合はその他（変数宣言・代入文など）
    return {
        "type": "other",
        "content": statement_str
    }



def parse_individual_statements(func_body):
    statements = []
    current_statement = []
    
    # 関数自体の開始中括弧 '{' と終了中括弧 '}' の中身だけをスキャン対象とする
    body_content = func_body.strip()
    if body_content.startswith('{') and body_content.endswith('}'):
        body_content = body_content[1:-1].strip()
        
    idx = 0
    length = len(body_content)
    control_keywords = ["for", "if", "while", "switch", "else"]
    
    while idx < length:
        # 現在の位置から制御構文キーワードが始まっているか確認
        is_control = False
        for kw in control_keywords:
            if body_content.startswith(kw, idx):
                next_char_idx = idx + len(kw)
                if next_char_idx < length and (body_content[next_char_idx].isspace() or body_content[next_char_idx] == '(' or body_content[next_char_idx] == '{'):
                    is_control = True
                    break
                    
        if is_control:
            if current_statement:
                prefix = "".join(current_statement).strip()
                if prefix:
                    statements.append(classify_statement_type(prefix))
                current_statement = []
                
            # 制御構文ブロック全体の閉じ中括弧 '}' の位置を特定
            end_brace_idx = find_control_block_end(body_content, idx)
            control_block_str = body_content[idx:end_brace_idx + 1].strip()
            
            statements.append({
                "type": "control",
                "content": control_block_str
            })
            
            idx = end_brace_idx + 1
            continue
            
        char = body_content[idx]
        current_statement.append(char)
        
        # コロンによるラベル文の判定
        if char == ':':
            statement_str = "".join(current_statement).strip()
            # 末尾のコロンを除いた識別子部分を抽出
            label_name = statement_str[:-1].strip()
            
            # C言語の有効な識別子（英数字・アンダースコア）のみで構成されているか判定
            # 三項演算子の「?」や、switch文の「case」「default」を除外する安全弁
            if label_name and all(c.isalnum() or c == '_' for c in label_name):
                if label_name != "default" and not label_name.startswith("case") and "?" not in "".join(current_statement):
                    statements.append(classify_statement_type(statement_str))
                    current_statement = []
                    idx += 1
                    continue
        
        if char == ';':
            statement_str = "".join(current_statement).strip()
            if statement_str:
                statements.append(classify_statement_type(statement_str))
            current_statement = []
            
        idx += 1
        
    if current_statement:
        remaining = "".join(current_statement).strip()
        if remaining:
            statements.append(classify_statement_type(remaining))
            
    return statements



def print_parsed_project_data(all_project_data):
    print("\n--- research_func_in_file ------------------")
    # 辞書データの1次元目（ファイルパス）と2次元目（関数名）を走査して外枠を出力する
    for file_path, functions_dict in all_project_data.items():
        print(f"[File]: {file_path}")
        
        for func_name, statements_list in functions_dict.items():
            print(f"  [Function]: {func_name}")
            
            # 各関数内部の処理リスト（3次元目）を走査
            for idx, statement_dict in enumerate(statements_list):
                print(f"    - 処理 {idx} つ目:")
                # 階層ネスト出力専門の部品関数を呼び出し、初期インデントレベル（3）を指定して委譲
                print_statement_node_recursive(statement_dict, indent_level=3)
        print("\n")

def print_statement_node_recursive(statement_dict, indent_level):
    # インデントレベルに応じた空白文字列を動的に生成（インデント1につき半角スペース4つ）
    base_indent = " " * (indent_level * 4)
    child_indent = " " * ((indent_level + 1) * 4)
    
    # 処理のタイプに応じた視覚的識別子（メタ情報）を決定
    st_type = statement_dict.get("type", "other")
    type_label = f"[{st_type.upper()}]"
    
    # ステートメントのコード内容（content）を出力
    print(f"{base_indent}{type_label}")
    print(f"{child_indent}{statement_dict.get('content', '')}")
    
    # "children"キーが存在し、かつ内部に下層の処理リストが格納されているかを判定
    children_list = statement_dict.get("children")
    if children_list and isinstance(children_list, list):
        # 下層の子供たちの要素を走査
        for c_idx, child_dict in enumerate(children_list):
            print(f"{child_indent}  * 内包処理 {c_idx} つ目:")
            # インデントレベルを+1加算して、自律的に下層の出力処理を反復呼び出し（再帰）する
            print_statement_node_recursive(child_dict, indent_level=indent_level + 2)


def split_control_header_and_body(statement_str):
    """
    中括弧のない制御構文の文字列から、制御ヘッダーと実行文のボディを分離する関数。
    例: 'else if (cond) stmt;' -> ('else if (cond)', 'stmt;')
    """
    length = len(statement_str)
    idx = 0
    
    # 制御構文の最初のキーワード（if, else, for, whileなど）をスキップ
    while idx < length and statement_str[idx].isalpha():
        idx += 1
        
    # キーワードの直後に if が続くケース（else if 構文など）への対応
    while idx < length:
        while idx < length and statement_str[idx].isspace():
            idx += 1
        if idx < length and statement_str.startswith("if", idx):
            idx += 2
        else:
            break
            
    # キーワード群と条件式の間の空白をスキップ
    while idx < length and statement_str[idx].isspace():
        idx += 1
        
    # 条件式の丸括弧が存在する場合は、ペアカウントを用いてその範囲を完全にスキップ
    if idx < length and statement_str[idx] == '(':
        paren_count = 0
        while idx < length:
            if statement_str[idx] == '(':
                paren_count += 1
            elif statement_str[idx] == ')':
                paren_count -= 1
                if paren_count == 0:
                    idx += 1
                    break
            idx += 1
            
    # 条件式終了後から、実際の単一実行文が始まるまでの空白をスキップ
    while idx < length and statement_str[idx].isspace():
        idx += 1
        
    # 算出された境界インデックスを用いて、ヘッダーとボディを完全に分離
    header_str = statement_str[:idx].strip()
    body_str = statement_str[idx:].strip()
    
    return header_str, body_str


def normalize_single_statement_block(header_str, body_str):
    """
    分離されたヘッダーと単一実行文のボディを受け取り、
    ボディを中括弧で物理的に包み込んだ完全なブロック文字列として再構築する関数。
    """
    if not body_str:
        return f"{header_str} {{}}"
        
    return f"{header_str} {{ {body_str} }}"



def parse_control_content_recursive(control_content):
    """
    制御構文ブロックの内部を解析し、ネストされた制御構造を再帰的に解体する関数。
    中括弧のない単一ステートメントは、物理的に中括弧を追加して文字列を再構築する。
    再構築された正規化文字列と、内包処理リストのタプルを返却する。
    """
    content_str = control_content.strip()
    
    # 制御構文のヘッダー（キーワードや丸括弧条件式）の終わりと、開始中括弧の位置を探索
    start_brace_idx = content_str.find('{')
    
    # 1. 開始中括弧が存在しない場合（中括弧のない単一ステートメントの救済）
    if start_brace_idx == -1:
        # 既存関数を用いてヘッダーとボディを安全に分離
        header_str, body_str = split_control_header_and_body(content_str)
        
        # 既存関数を用いて中括弧を物理的に付与した正規化文字列を生成
        normalized_content = normalize_single_statement_block(header_str, body_str)
        
        if not body_str:
            return [], normalized_content
            
        # 抽出フェーズにおいてあえて物理的に中括弧で囲み、すべての制御構文が中括弧ブロックを伴う前提を保証する
        wrapped_body = f"{{{body_str}}}"
        
        # 関数自体の開始中括弧と終了中括弧の中身だけをスキャン対象とするロジックと同期させ、
        # 物理的に追加した中括弧の中身の単一文を抽出し、さらにネストがあれば再帰解体する
        internal_statements = parse_individual_statements(wrapped_body)
        
        for item in internal_statements:
            if item.get("type") == "control":
                child_statements, child_normalized_content = parse_control_content_recursive(item.get("content", ""))
                item["children"] = child_statements
                item["content"] = child_normalized_content
                
        return internal_statements, normalized_content
        
    # 2. 開始中括弧が存在する場合（通常の中括弧ブロック記述）
    else:
        end_brace_idx = content_str.rfind('}')
        if end_brace_idx == -1 or start_brace_idx >= end_brace_idx:
            return [], content_str
            
        # 既存の完成された文字スキャン関数に投入し、下層の処理として一次分解する
        inner_body = content_str[start_brace_idx + 1:end_brace_idx].strip()
        if not inner_body:
            return [], content_str
            
        internal_statements = parse_individual_statements(content_str[start_brace_idx:end_brace_idx + 1])
        
    # 切り出された内部処理リストを走査し、さらにネストされたcontrolブロックがあれば再帰的に解体する
    for item in internal_statements:
        if item.get("type") == "control":
            child_statements, child_normalized_content = parse_control_content_recursive(item.get("content", ""))
            item["children"] = child_statements
            item["content"] = child_normalized_content
            
    return internal_statements, content_str



def deep_parse_control_blocks(all_project_data):
    """
    プロジェクト全体の3次元辞書データを走査し、
    各関数のステートメントリスト内の制御構文内部ブロックを再帰的に解体・抽象化する関数。
    中括弧が補完された正規化文字列を受け取り、親ノードのcontentを上書き更新する。
    """
    for file_path, functions_dict in all_project_data.items():
        for func_name, statements_list in functions_dict.items():
            for statement in statements_list:
                if statement.get("type") == "control":
                    content_str = statement.get("content", "")
                    
                    child_statements, normalized_content = parse_control_content_recursive(content_str)
                    
                    statement["children"] = child_statements
                    statement["content"] = normalized_content
                    
    return all_project_data


def extract_functions_from_files(c_file_paths):
    all_project_data = {}
    
    for file_path in c_file_paths:
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()
            
        # コメントを除外したクリーンなコードを取得
        clean_code = remove_comments(source_code)
        
        # ファイル内に存在する関数定義（関数名と関数内部のコード体）のペアを取得
        function_definitions = find_function_definitions(clean_code)
        
        # 全体辞書に対し、ファイルパスをキーとして関数用の空の辞書を登録
        all_project_data[file_path] = {}
        
        for func_name, func_body in function_definitions:
            # 関数内部の文字列から個々の処理（ステートメント）を切り出す
            statements = parse_individual_statements(func_body)
            
            if not statements or statements[-1].get("type") != "return":
                statements.append({
                    "type": "return",
                    "content": "return;"
                })
            
            # 関数用辞書に対し、関数名をキーとして処理のリストを登録
            all_project_data[file_path][func_name] = statements
            
    # 直列的な後処理として、controlブロックの深層解体を実行する
    all_project_data = deep_parse_control_blocks(all_project_data)
    
    print_parsed_project_data(all_project_data)
    return all_project_data


def convert_statements_to_nodes(statements_list, file_path):
    """
    ステートメントリスト全体を直列走査する主エントリポイント関数。
    各ノードへファイルパス情報をリレーするため、引数にfile_pathを追加。
    """
    abstract_nodes = []
    idx = 0
    length = len(statements_list)
    
    while idx < length:
        current_st = statements_list[idx]
        st_type = current_st.get("type")
        content_str = current_st.get("content", "").strip()
        
        # if文を検知した場合、結合処理の専門関数へとインデックス制御とfile_pathを委託
        if st_type == "control" and content_str.startswith("if"):
            condition_node, next_idx = combine_if_else_conditional_chain(statements_list, idx, file_path)
            if condition_node:
                abstract_nodes.append(condition_node)
            idx = next_idx
            continue
            
        # if文以外のすべての文は直接中央ディスパッチャへfile_pathと共に委託
        else:
            abstract_node = dispatch_statement_to_node(current_st, file_path)
            if abstract_node:
                abstract_nodes.append(abstract_node)
                
        idx += 1
        
    return abstract_nodes



def combine_if_else_conditional_chain(statements_list, current_idx, file_path):
    """
    if文の直後に連続するelse/else ifの範囲をルックアヘッドによって特定し、
    単一のConditionNodeに対してすべてのブランチを直列に統合・結合する関数。
    各ブランチの下層ノードへfile_pathをリレーするため、引数を拡張。
    """
    length = len(statements_list)
    if current_idx >= length:
        return None, current_idx
        
    # 初段のif文を中央ディスパッチャを介して解析し、ConditionNodeの骨格を生成
    first_st = statements_list[current_idx]
    base_condition_node = dispatch_statement_to_node(first_st, file_path)
    
    next_idx = current_idx + 1
    
    # 直後に連続するelse/else ifをルックアヘッドして範囲特定と結合を行う
    while next_idx < length:
        next_st = statements_list[next_idx]
        next_content = next_st.get("content", "").strip()
        
        if next_st.get("type") == "control" and next_content.startswith("else"):
            parsed_branch_node = dispatch_statement_to_node(next_st, file_path)
            if parsed_branch_node and "branches" in parsed_branch_node:
                base_condition_node["branches"].extend(parsed_branch_node["branches"])
            next_idx += 1
        else:
            break
            
    return base_condition_node, next_idx



def dispatch_statement_to_node(statement_dict, file_path):
    """
    ステートメントのタイプやキーワードを判別し、それぞれの構文解析を専門とする
    個別関数へとfile_pathを伴って処理を振り分ける中央ディスパッチャ関数。
    """
    st_type = statement_dict.get("type")
    content_str = statement_dict.get("content", "").strip()
    
    if st_type == "control":
        if (content_str.startswith("if") or 
            content_str.startswith("else") or 
            content_str.startswith("switch")):
            return parse_to_condition_node(statement_dict, file_path)
            
        elif content_str.startswith("for") or content_str.startswith("while"):
            return parse_to_loop_node(statement_dict, file_path)
            
    return parse_to_action_node(statement_dict, file_path)



def parse_to_condition_node(statement_dict, file_path):
    """
    分岐構文（if, else, switch）の文字列解析を専門に行い、
    C言語の属性を剥ぎ取ったConditionNodeを生成する関数
    """
    content_str = statement_dict.get("content", "").strip()
    children = statement_dict.get("children", [])
    
    abstract_children = []
    if children:
        abstract_children = convert_statements_to_nodes(children, file_path)
        
    condition_text = "else"
    
    if content_str.startswith("switch"):
        start_paren = content_str.find("(")
        if start_paren != -1:
            paren_count = 0
            end_paren = -1
            for i in range(start_paren, len(content_str)):
                if content_str[i] == '(':
                    paren_count += 1
                elif content_str[i] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        end_paren = i
                        break
            if end_paren != -1:
                condition_text = content_str[start_paren + 1:end_paren].strip()
                
        return {
            "node_type": "ConditionNode",
            "file_path": file_path,
            "branches": [
                {
                    "condition": f"switch ({condition_text})",
                    "body": abstract_children
                }
            ]
        }
        
    if "if" in content_str:
        start_paren = content_str.find("(")
        if start_paren != -1:
            paren_count = 0
            end_paren = -1
            for i in range(start_paren, len(content_str)):
                if content_str[i] == '(':
                    paren_count += 1
                elif content_str[i] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        end_paren = i
                        break
            if end_paren != -1:
                condition_text = content_str[start_paren + 1:end_paren].strip()
                
    return {
        "node_type": "ConditionNode",
        "file_path": file_path,
        "branches": [
            {
                "condition": condition_text,
                "body": abstract_children
            }
        ]
    }



def parse_to_loop_node(statement_dict, file_path):
    """
    反復構文（for, while）の文字列解析を行い、範囲情報を抽象化したLoopNodeを生成する関数。
    不要な分解前の生コード全体文字列は破棄し、パラメータと子ノードのみを精製する。
    """
    content_str = statement_dict.get("content", "").strip()
    children = statement_dict.get("children", [])
    
    abstract_children = []
    if children:
        abstract_children = convert_statements_to_nodes(children, file_path)
        
    index_var = "unknown"
    start_val = "unknown"
    end_val = "unknown"
    
    if content_str.startswith("for"):
        start_paren = content_str.find("(")
        end_paren = content_str.find(")")
        if start_paren != -1 and end_paren != -1:
            for_expr = content_str[start_paren + 1:end_paren].strip()
            parts = for_expr.split(";")
            if len(parts) >= 2:
                init_match = re.search(r'(?:\w+\s+)?(\w+)\s*=\s*([^;]+)', parts[0])
                if init_match:
                    index_var = init_match.group(1).strip()
                    start_val = init_match.group(2).strip()
                    
                cond_match = re.search(r'<\s*([^;]+)', parts[1])
                if cond_match:
                    end_val = f"{cond_match.group(1).strip()} - 1"
                else:
                    cond_match_le = re.search(r'<=\s*([^;]+)', parts[1])
                    if cond_match_le:
                        end_val = cond_match_le.group(1).strip()
                        
    elif content_str.startswith("while"):
        start_paren = content_str.find("(")
        end_paren = content_str.rfind(")")
        if start_paren != -1 and end_paren != -1:
            start_val = "0"
            end_val = content_str[start_paren + 1:end_paren].strip()
            index_var = "condition"
            
    return {
        "node_type": "LoopNode",
        "index_var": index_var,
        "start": start_val,
        "end": end_val,
        "file_path": file_path,
        "body": abstract_children
    }


def parse_to_action_node(statement_dict, file_path):
    """
    制御構文以外のステートメント（関数呼び出し、return、break/continue、その他）を
    ActionNodeへとマッピングし、逆引き用のfile_pathを付与してクリーンに抽象化する関数。
    """
    st_type = statement_dict.get("type")
    content_str = statement_dict.get("content", "").strip()
    
    action_map = {
        "function_call": "call",
        "return": "return",
        "loop_end": "loop_control",
        "label": "label",
        "other": "statement"
    }
    
    return {
        "node_type": "ActionNode",
        "action_type": action_map.get(st_type, "statement"),
        "content": content_str,
        "file_path": file_path
    }


def print_abstract_ir_project_data(parsed_functions_list):
    """
    抽象中間表現（IR）ノードが追加されたプロジェクト全体の関数リストを走査し、
    ネストされた階層構造（AST）をインデント付きでデバッグ用にコンソールへ出力する関数。
    """
    print("\n--- abstract_ir_generator ------------------")
    for func_info in parsed_functions_list:
        func_name = func_info.get("name", "unknown")
        file_path = func_info.get("file_path", "unknown")
        
        print(f"--- Function: {func_name} ({file_path}) ---")
        abstract_nodes = func_info.get("abstract_nodes", [])
        
        for node in abstract_nodes:
            print_node_recursive(node, indent_level=1)


def print_node_recursive(node, indent_level):
    """
    個々の抽象中間表現（IR）ノードの内容を出力し、
    制御構文ノードの場合は内部の子ノードリスト（body）を再帰的に走査して出力する補助関数。
    """
    indent = "  " * indent_level
    node_type = node.get("node_type", "unknown")
    
    print(f"{indent}Node Type: {node_type}")
    
    # 処理系ノード（ActionNode）の個別情報の出力
    if node_type == "ActionNode":
        print(f"{indent}  Action Type: {node.get('action_type')}")
        print(f"{indent}  Content: {node.get('content')}")
        
    # 反復構文ノード（LoopNode）のパラメータ出力と内部ボディの再帰走査
    elif node_type == "LoopNode":
        print(f"{indent}  Index Var: {node.get('index_var')}")
        print(f"{indent}  Range: {node.get('start')} -> {node.get('end')}")
        
        body_nodes = node.get("body", [])
        if body_nodes:
            print(f"{indent}  Body:")
            for child in body_nodes:
                print_node_recursive(child, indent_level + 2)
                
    # 分岐構文ノード（ConditionNode）のパラメータ出力と各ブランチ内部ボディの再帰走査
    elif node_type == "ConditionNode":
        branches = node.get("branches", [])
        for idx, branch in enumerate(branches):
            print(f"{indent}  Branch {idx}:")
            print(f"{indent}    Condition: {branch.get('condition')}")
            
            body_nodes = branch.get("body", [])
            if body_nodes:
                print(f"{indent}    Body:")
                for child in body_nodes:
                    print_node_recursive(child, indent_level + 3)



def generate_project_abstract_ir(all_project_data):
    """
    プロジェクト全体の多次元辞書データを直列に走査し、
    ファイルパスの逆引き情報を持った関数オブジェクトのリストへと
    データ構造を完全に組み替えて抽象中間表現（IR）を生成するトップエントリポイント関数。
    """
    abstracted_project_functions_list = []
    
    # 第1次元：ファイルパスをキーとする辞書からパスと関数辞書を展開
    for file_path, functions_dict in all_project_data.items():
        
        # 第2次元：関数名をキーとする辞書から関数名とステートメントのリストを展開
        for func_name, statements_list in functions_dict.items():
            
            # 第3次元：ステートメントのリストを抽象IRノードの直列リストへ変換委託
            # 逆引きを可能とするため、対象のファイルパスを引数として確実にリレーする
            abstract_nodes = convert_statements_to_nodes(statements_list, file_path)
            
            # 1つの関数を一元管理するクリーンな関数オブジェクト（関数ノード）を構築
            func_info = {
                "name": func_name,
                "file_path": file_path,
                "abstract_nodes": abstract_nodes
            }
            
            abstracted_project_functions_list.append(func_info)
            
    # デバッグ用に、一元化された構造を安全にコンソールへ出力する関数へ委託
    print_abstract_ir_project_data(abstracted_project_functions_list)
    
    return abstracted_project_functions_list



def find_return_node_pointer(abstract_nodes):
    """
    呼び出し先関数のノードリストを末尾から逆方向に走査し、
    returnを持つActionNode（存在しない場合は最終要素）への参照ポインタを返す関数。
    """
    if not abstract_nodes:
        return None
        
    # 末尾から逆方向に走査して return ノードを探索
    for node in reversed(abstract_nodes):
        if node.get("node_type") == "ActionNode" and node.get("action_type") == "return":
            return node
            
    # return が存在しない場合はリストの最終要素を返却
    return abstract_nodes[-1]


def build_function_lookup_map(abstracted_project_functions_list):
    """
    プロジェクト全体の関数リストから、関数名をキーとし、
    その関数のabstract_nodesへの参照を値としたO(1)探索用のハッシュマップを構築する関数。
    """
    function_map = {}
    
    for func_info in abstracted_project_functions_list:
        func_name = func_info.get("name")
        abstract_nodes = func_info.get("abstract_nodes")
        
        if func_name:
            function_map[func_name] = abstract_nodes
            
    return function_map


def attach_jump_links_to_call_node(statement_dict, function_map):
    """
    単一のCallノードに対して、ハッシュマップから呼び出し先関数を検索し、
    進入ポインタ(jump_destination)と復帰ポインタ(jump_return)を動的に拡張・付与する関数。
    """
    if statement_dict.get("node_type") != "ActionNode" or statement_dict.get("action_type") != "call":
        return

    content_str = statement_dict.get("content", "").strip()
    
    # 代入文を伴う形式（変数 = 関数名(...)）も含め、呼び出されている関数名を正確に抽出
    # 最初に出現する「単語 + 開き丸括弧」の組み合わせを探索する
    match = re.search(r'\b(\w+)\s*\(', content_str)
    if not match:
        return
        
    called_func_name = match.group(1)
    
    # ハッシュ探索用マップから呼び出し先関数のノードリストをO(1)で引き当てる
    target_abstract_nodes = function_map.get(called_func_name)
    
    if target_abstract_nodes:
        # 1. 進入ポインタ：呼び出し先関数のノードリストの先頭要素への参照を格納
        statement_dict["jump_destination"] = target_abstract_nodes[0]
        
        # 2. 復帰ポインタ：専門の探索関数を呼び出して return ノード（または最終要素）への参照を格納
        return_node_pointer = find_return_node_pointer(target_abstract_nodes)
        statement_dict["jump_return"] = return_node_pointer


def traverse_and_resolve_links_recursive(nodes_list, function_map):
    """
    IRの木構造を再帰的に走査し、Callノードを発見した際に
    専門のリンク付与関数を呼び出して参照ポインタを拡張する関数。
    """
    for node in nodes_list:
        # ActionNode(call) を検知した場合はリンクを付与
        if node.get("node_type") == "ActionNode" and node.get("action_type") == "call":
            attach_jump_links_to_call_node(node, function_map)
            
        # ConditionNode の場合、各ブランチの body を再帰的に走査
        elif node.get("node_type") == "ConditionNode":
            for branch in node.get("branches", []):
                traverse_and_resolve_links_recursive(branch.get("body", []), function_map)
                
        # LoopNode の場合、body を再帰的に走査
        elif node.get("node_type") == "LoopNode":
            traverse_and_resolve_links_recursive(node.get("body", []), function_map)


def print_linked_ir_project_data(abstracted_project_functions_list):
    """
    関数呼び出しリンクが拡張されたプロジェクト全体のIRデータを、
    デバッグ用にコンソールへ可視化するエントリポイント関数。
    """
    print("\n--- abstract_ir_linkers ------------------")
    for func_info in abstracted_project_functions_list:
        func_name = func_info.get("name", "unknown")
        file_path = func_info.get("file_path", "unknown")
        print(f"--- Function: {func_name} ({file_path}) ---")
        
        for node in func_info.get("abstract_nodes", []):
            print_linked_node_recursive(node, indent_level=1)


def print_linked_node_recursive(node, indent_level):
    """
    リンク情報を含む抽象中間表現ノードを再帰的に出力する関数。
    """
    indent = "  " * indent_level
    node_type = node.get("node_type", "unknown")
    print(f"{indent}Node Type: {node_type}")
    
    # ノード情報の出力
    if node_type == "ActionNode":
        print(f"{indent}  Action Type: {node.get('action_type')}")
        print(f"{indent}  Content: {node.get('content')}")
        # リンク情報の出力
        if "jump_destination" in node or "jump_return" in node:
            print(f"{indent}  [Link Info]:")
            if node.get("jump_destination"):
                dest = node["jump_destination"]
                print(f"{indent}    -> jump_destination: {dest.get('node_type')} ({dest.get('action_type', '')}: {dest.get('content', '')[:20]}...)")
            if node.get("jump_return"):
                ret = node["jump_return"]
                print(f"{indent}    -> jump_return: {ret.get('node_type')} ({ret.get('action_type', '')}: {ret.get('content', '')[:20]}...)")
                
    elif node_type == "LoopNode":
        print(f"{indent}  Index Var: {node.get('index_var')}")
        for child in node.get("body", []):
            print_linked_node_recursive(child, indent_level + 2)
            
    elif node_type == "ConditionNode":
        for idx, branch in enumerate(node.get("branches", [])):
            print(f"{indent}  Branch {idx}:")
            print(f"{indent}    Condition: {branch.get('condition')}")
            for child in branch.get("body", []):
                print_linked_node_recursive(child, indent_level + 3)


def link_project_function_calls(abstracted_project_functions_list):
    """
    プロジェクト全体のIRに対し、ハッシュマップを用いて関数間の往復参照リンクを構築・内包させるメインエントリポイント関数。
    """
    # 1. 探索用マップを構築
    function_map = build_function_lookup_map(abstracted_project_functions_list)
    
    # 2. 全関数を走査してリンクを解決
    for func_info in abstracted_project_functions_list:
        abstract_nodes = func_info.get("abstract_nodes", [])
        traverse_and_resolve_links_recursive(abstract_nodes, function_map)

    print_linked_ir_project_data(abstracted_project_functions_list)
    return abstracted_project_functions_list



def build_function_lookup_map(abstracted_project_functions_list):
    """
    プロジェクト内の全関数を走査し、関数名をキー、その関数情報（抽象化ノードリスト）
    を値として保持するハッシュ探索用マップを構築する。
    """
    function_map = {}
    for func_info in abstracted_project_functions_list:
        func_name = func_info.get("name")
        if func_name:
            function_map[func_name] = func_info.get("abstract_nodes", [])
    return function_map

def find_main_function_node(abstracted_project_functions_list):
    """
    プロジェクト全体の関数リストからnameがmainであるものを探索し、
    そのabstract_nodesリストの参照を返す関数。
    """
    for func_info in abstracted_project_functions_list:
        if func_info.get("name") == "main":
            return func_info.get("abstract_nodes", [])
    return []


def append_to_schedule(node, scheduled_list):
    """
    指定されたノードを時系列スケジュール配列に安全に追加する関数。
    """
    if node:
        scheduled_list.append(node)



def handle_call_node_scheduling(call_node, function_map, scheduled_list, call_stack):
    """
    関数呼び出しノードを処理する専門ハンドラ。
    呼び出し元ノードのcontentから正規表現を用いて呼び出し先関数名を正確に抽出し、
    コールスタックによる無限再帰検知を行いながら、呼び出し先関数の内部ノードを時系列スケジュールに再帰展開する。
    末尾ノードの重複登録を避けるため、再帰走査側への委譲に一元化する。
    """
    # 1. 呼び出し元ノードをスケジュールに記録
    scheduled_list.append(call_node)
    
    # 2. 呼び出し元ノード自身のcontentから、正規表現を用いて純粋な関数名（文字列）を正確に抽出
    content_str = call_node.get("content", "").strip()
    match = re.search(r'\b(\w+)\s*\(', content_str)
    
    if match:
        destination_func_name = match.group(1)
        
        # 3. コールスタックを用いて無限再帰（循環参照）を厳格に検知
        if destination_func_name in call_stack:
            sys.stderr.write(
                f"[ERROR] Infinite recursion detected: "
                f"Function '{destination_func_name}' is called circularly. "
                f"Current Call Stack: {call_stack}\n"
            )
            sys.exit(1)
        
        # 4. 呼び出し先関数名をスタックに登録して遷移
        call_stack.append(destination_func_name)
        
        # 探索用マップから呼び出し先関数の本体（抽象化ノードリスト）を取得して再帰走査
        called_function_nodes = function_map.get(destination_func_name, [])
        serialize_nodes_recursive(called_function_nodes, function_map, scheduled_list, call_stack)
        
        # 5. 呼び出し先関数の走査完了後、スタックから削除して復帰
        call_stack.pop()



def handle_condition_node_scheduling(condition_node, function_map, scheduled_list, call_stack):
    """
    ConditionNodeを受け取り、内包される全ブランチのbodyを再帰走査関数に委譲する関数。
    後続フェーズがPlantUMLのelseおよびendを検知できるよう、ブランチ境界マーカーとBlockEndNodeをスケジュールに挿入する。
    """
    # 1. 条件分岐の開始ノードをスケジュールに記録（出力側はここでaltを認識する）
    scheduled_list.append(condition_node)
    
    branches = condition_node.get("branches", [])
    
    for idx, branch in enumerate(branches):
        # 2. 2つ目以降のブランチ（else if / else）の走査直前に、境界マーカーノードを挿入
        if idx > 0:
            branch_marker = {
                "node_type": "BranchMarkerNode",
                "condition": branch.get("condition", "else")
            }
            scheduled_list.append(branch_marker)
        
        # 3. 各ブランチのbodyに含まれるノードリストを再帰的に走査してスケジュールに追加
        serialize_nodes_recursive(branch.get("body", []), function_map, scheduled_list, call_stack)
        
    # 4. すべてのブランチの走査完了後、条件分岐全体の終端を示すBlockEndNodeを確実に挿入
    block_end_node = {
        "node_type": "BlockEndNode"
    }
    scheduled_list.append(block_end_node)



def handle_loop_node_scheduling(loop_node, function_map, scheduled_list, call_stack):
    """
    LoopNodeを受け取り、内包されるbodyのノードリストを再帰走査関数に委譲する関数。
    後続フェーズがPlantUMLのendおよびインデント復帰を検知できるよう、BlockEndNodeをスケジュールに挿入する。
    """
    # 1. ループの開始ノードをスケジュールに記録（出力側はここでloopを認識する）
    scheduled_list.append(loop_node)
    
    # 2. ループのbodyに含まれるノードリストを再帰的に走査してスケジュールに追加
    serialize_nodes_recursive(loop_node.get("body", []), function_map, scheduled_list, call_stack)
    
    # 3. ループ全体の終端を示すBlockEndNodeを確実に挿入
    block_end_node = {
        "node_type": "BlockEndNode"
    }
    scheduled_list.append(block_end_node)




def serialize_nodes_recursive(nodes_list, function_map, scheduled_list, call_stack):
    """
    ノードリストを巡回し、ノードの属性に応じて各専門ハンドラ関数へ処理を振り分けるディスパッチャ関数。
    無限再帰防止のためのcall_stackを各ハンドラへ正確に伝播させる。
    """
    for node in nodes_list:
        node_type = node.get("node_type")
        
        if node_type == "ActionNode":
            if node.get("action_type") == "call":
                handle_call_node_scheduling(node, function_map, scheduled_list, call_stack)
            else:
                scheduled_list.append(node)
                
        elif node_type == "ConditionNode":
            handle_condition_node_scheduling(node, function_map, scheduled_list, call_stack)
            
        elif node_type == "LoopNode":
            handle_loop_node_scheduling(node, function_map, scheduled_list, call_stack)




def calculate_next_indent_level(node, current_indent):
    """
    ノードの属性や内部構造を解析し、時系列が次の階層に深く潜るべきか、
    あるいは元の階層に復帰すべきかを判定して、次に適用すべきインデントの深さを計算して返却する関数。
    """
    node_type = node.get("node_type")
    calculated_indent = current_indent
    
    if node_type == "ConditionNode":
        branches = node.get("branches", [])
        for b_idx, branch in enumerate(branches):
            condition = branch.get("condition", "else")
            # 各ブランチの条件式を漏れなく出力
            print(f"{'    ' * current_indent}  [Branch Info] Index: {b_idx}, Condition: {condition}")
        # ブロック内部へ進入するためインデントを増加
        calculated_indent = current_indent + 1
        
    elif node_type == "LoopNode":
        index_var = node.get("index_var")
        # 上流のデータ構造に合わせ、startとendのキーからそれぞれ範囲情報を確実に取得
        start_val = node.get("start", "unknown")
        end_val = node.get("end", "unknown")
        range_info = f"{start_val} -> {end_val}"
        
        # ループの情報を詳細に出力
        print(f"{'    ' * current_indent}  [Loop Info] Var: {index_var}, Range: {range_info}")
        # ブロック内部へ進入するためインデントを増加
        calculated_indent = current_indent + 1
        
    elif node_type == "BlockEndNode":
        # ブロックの終端を示すノード属性を検知した場合はインデントを減少
        calculated_indent = current_indent - 1
        if calculated_indent < 0:
            calculated_indent = 0
            
    return calculated_indent


def print_single_node_with_indent(index, node, indent_level):
    """
    単一のノードの型を識別し、現在のインデント深さに応じた空白スペースを付与して出力する関数。
    ノードの属性に応じて次のインデントレベルを計算し、呼び出し元へ返却する。
    """
    node_type = node.get("node_type")
    
    # 現在のインデントレベルに応じた空白文字列を生成（1レベル＝4スペース）
    indent_space = "    " * indent_level
    
    # 時系列順序を示すインデックスとノード型を出力
    print(f"{indent_space}[{index:03d}] Node Type: {node_type}")
    
    # ノード型に応じた詳細情報の出力とインデントの計算
    if node_type == "ActionNode":
        action_type = node.get("action_type")
        content = node.get("content")
        print(f"{indent_space}      [Action] Type: {action_type}, Content: {content}")
        # 通常のアクションノードはインデントを変更しない
        next_indent_level = indent_level
        
    elif node_type in ("ConditionNode", "LoopNode", "BlockEndNode"):
        # 構造の分岐・反復・終端を司るノードは専門関数にインデント計算と詳細出力を委譲
        next_indent_level = calculate_next_indent_level(node, indent_level)
        
    else:
        # 未知のノード型に対するフォールバック
        next_indent_level = indent_level
        
    return next_indent_level



def print_scheduled_ir_data(scheduled_execution_list):
    """
    時系列順に平坦化された抽象化ノードのスケジュール配列を走査し、
    各ノードの階層の深さ（インデント）を正確に管理しながらコンソールへ出力するメイン統括関数。
    """
    print("\n--- Scheduled Execution Sequence ---")
    
    # ネストの深さを物理的に管理するための整数型変数を初期化
    current_indent_level = 0
    
    # スケジュールリストを先頭から時系列順に1要素ずつ走査
    for index, node in enumerate(scheduled_execution_list):
        # 単一ノード出力専門関数へ処理を委譲し、次のノードのための最新のインデント深さを受け取る
        current_indent_level = print_single_node_with_indent(
            index, 
            node, 
            current_indent_level
        )

def generate_execution_schedule(abstracted_project_functions_list):
    """
    スケジューリングフェーズの窓口関数。全体の初期化と走査を統括し、
    無限再帰を防止するためのコールスタックを管理しながら
    時系列に平坦化された実行スケジュール配列を返却する。
    """
    # 1. 効率的な関数探索のためハッシュマップを構築
    function_map = build_function_lookup_map(abstracted_project_functions_list)
    
    # 2. 時系列の起点となるmain関数のノードリストを取得
    main_nodes = find_main_function_node(abstracted_project_functions_list)
    
    # 3. 最終的な直列スケジュール配列を初期化
    scheduled_execution_list = []
    
    # 4. 無限再帰・循環参照検知用のコールスタックを初期化し、起点を登録
    call_stack = []
    call_stack.append("main")
    
    # 5. コールスタックを伝播させながら、再帰的シリアライズ処理を開始
    serialize_nodes_recursive(main_nodes, function_map, scheduled_execution_list, call_stack)

    # 6. returnの直前に平坦化されたスケジュールデータのログ出力関数をコール
    print_scheduled_ir_data(scheduled_execution_list)
    
    return scheduled_execution_list


def extract_target_function_name(content_str):
    """
    C言語の関数呼び出し文字列から、正規表現を用いて純粋な関数名のみを抽出する関数。
    """
    match = re.search(r'\b(\w+)\s*\(', content_str)
    if match:
        return match.group(1)
    return None

def build_defined_functions_set(abstracted_project_functions_list):
    """
    プロジェクト内に実際に定義されている関数の名前を抽出し、
    ハッシュ探索が高速な集合（set）として構築する関数。
    """
    defined_functions = set()
    for func_info in abstracted_project_functions_list:
        func_name = func_info.get("name")
        if func_name:
            defined_functions.add(func_name)
    return defined_functions

def write_lines_to_pu_file(all_lines_list, output_file_path):
    """
    書き出すべきPlantUMLコマンドの全行リストを受け取り、
    指定されたパスのファイルへ改行コード付きで純粋に書き出す関数。
    """
    with open(output_file_path, "w", encoding="utf-8") as f:
        for line in all_lines_list:
            f.write(line + "\n")



def format_loop_node_lines(loop_node):
    """
    LoopNodeからindex_var、start、endの属性を正確に取得し、
    お客様の設計規則に従った形式のコマンド文字列リストを生成して返却する関数。
    """
    index_var = loop_node.get("index_var", "unknown")
    start = loop_node.get("start", "unknown")
    end = loop_node.get("end", "unknown")
    return [f"loop {index_var} ∈ [{start}, {end}]"]


def format_condition_node_lines(condition_node):
    """
    ConditionNodeに内包されている最初のブランチ（インデックス0）から条件式を取得し、
    UMLの分岐開始コマンド文字列リストを生成して返却する関数。
    """
    branches = condition_node.get("branches", [])
    condition = "unknown"
    if branches:
        condition = branches[0].get("condition", "unknown")
    return [f"alt {condition}"]


def format_branch_marker_node_lines(branch_marker_node):
    """
    BranchMarkerNodeが保持するcondition属性を取得し、
    排他分岐の切り替わりを示すUMLコマンド文字列リストを生成して返却する関数。
    """
    condition = branch_marker_node.get("condition", "else")
    return [f"else {condition}"]

def format_block_end_node_lines():
    """
    制御ブロックの終了を示す end の文字列コマンドを生成し、
    リスト形式で返却する関数。
    """
    return ["end"]


def generate_uml_header_lines(abstracted_project_functions_list):
    """
    @startumlから始まる初期宣言部を生成する関数。
    プロジェクト内関数のみをparticipantとして定義し、出自パスをコメントアウトとして埋め込む。
    """
    lines = []
    lines.append("@startuml")
    lines.append('actor "Host OS" as host')
    
    for func_info in abstracted_project_functions_list:
        func_name = func_info.get("name")
        file_path = func_info.get("file_path", "")
        if func_name:
            # プロジェクトルートからの相対パスをコメントアウト形式で埋め込む
            lines.append(f'participant "{func_name}" as {func_name} /\' {file_path} \'/')
            
    lines.append('participant "外部" as 外部')
    
    # シーケンスの初期キックを生成
    lines.append("host -> main : main()")
    lines.append("activate main")
    return lines


def generate_uml_footer_lines():
    """
    シーケンス図の終端宣言である @enduml のみを生成する関数。
    """
    return [
        "@enduml"
    ]

def handle_action_node_lines(action_node, current_call_stack, defined_functions_set):
    """
    ActionNodeを解析し、statementのスキップ、callによるメッセージ線とライフラインの活性化、
    returnによるメッセージ線とライフラインの非活性化を1対1で機械的にマッピングする関数。
    """
    action_type = action_node.get("action_type")
    content = action_node.get("content", "").strip()
    
    # C言語の文字列内の改行コード等を適切にエスケープ処理
    content_escaped = content.replace("\n", "\\n")
    
    # 1. statement（純粋な代入文等）の場合は、将来の拡張を見据えつつ、現段階では一律スキップ
    if action_type == "statement":
        return []
        
    # 2. 関数呼び出し（call）の場合の処理
    elif action_type == "call":
        lines = []
        caller = current_call_stack[-1] if current_call_stack else "main"
        
        # 提出済みの下流関数を用いて純粋な関数名を抽出
        target_func = extract_target_function_name(content)
        
        if target_func in defined_functions_set:
            # 内部関数の場合は呼び出し線を生成し、スタックを更新して活性化
            lines.append(f"{caller} -> {target_func} : {content_escaped}")
            lines.append(f"activate {target_func}")
            current_call_stack.append(target_func)
        else:
            # 外部関数の場合は一律で「外部」を宛先とし、即時復帰の往復ライフラインをセットで生成
            lines.append(f"{caller} -> 外部 : {content_escaped}")
            lines.append("activate 外部")
            lines.append(f"外部 -> {caller} : return")
            lines.append("deactivate 外部")
        return lines
        
    # 3. 関数からの復帰（return）の場合の処理
    elif action_type == "return":
        lines = []
        if len(current_call_stack) >= 2:
            current_func = current_call_stack[-1]
            caller_func = current_call_stack[-2]
            
            lines.append(f"{current_func} -> {caller_func} : {content_escaped}")
            lines.append(f"deactivate {current_func}")
            current_call_stack.pop()
        elif len(current_call_stack) == 1:
            current_func = current_call_stack[-1]
            lines.append(f"{current_func} -> host : {content_escaped}")
            lines.append(f"deactivate {current_func}")
            current_call_stack.pop()
        return lines
        
    return []


def generate_uml_body_lines(scheduled_execution_list, defined_functions_set):
    """
    平坦化された時系列リストを巡回し、ノードの型に応じて
    適切な文字列フォーマットハンドラへ処理を振り分け、全体の本体テキストを構築する関数。
    """
    body_lines = []
    current_call_stack = ["main"]
    
    for node in scheduled_execution_list:
        node_type = node.get("node_type")
        
        if node_type == "LoopNode":
            body_lines.extend(format_loop_node_lines(node))
            
        elif node_type == "ConditionNode":
            body_lines.extend(format_condition_node_lines(node))
            
        elif node_type == "BranchMarkerNode":
            body_lines.extend(format_branch_marker_node_lines(node))
            
        elif node_type == "BlockEndNode":
            body_lines.extend(format_block_end_node_lines())
            
        elif node_type == "ActionNode":
            body_lines.extend(handle_action_node_lines(node, current_call_stack, defined_functions_set))
            
    return body_lines


def execute_plantuml_translation(scheduled_execution_list, abstracted_project_functions_list, output_file_path):
    """
    UMLテキスト出力フェーズのトップエントリポイント。
    各部品関数を順番に直列呼び出しし、最終的な.puファイルを生成する役割に徹する。
    """
    # 1. 内部関数名のハッシュセットを事前構築
    defined_functions_set = build_defined_functions_set(abstracted_project_functions_list)
    
    # 2. 各セクションのPlantUMLコマンド文字列リストを順次生成
    header_lines = generate_uml_header_lines(abstracted_project_functions_list)
    body_lines = generate_uml_body_lines(scheduled_execution_list, defined_functions_set)
    footer_lines = generate_uml_footer_lines()
    
    # 3. 全行データを単一のリストに結合
    all_lines = header_lines + body_lines + footer_lines
    
    # 4. ファイル入出力関数へ委譲して書き出しを実行
    write_lines_to_pu_file(all_lines, output_file_path)


def main():
    # 対象となるC言語ソースコードが格納されたディレクトリパスを設定
    target_directory = "../prj_test"
    
    # 出力先となるPlantUMLシーケンス図ファイルのパスを設定
    output_file_path = "output.pu"
    
    # 指定ディレクトリ以下のすべてのC言語ファイルパスを探索・取得
    c_file_list = fetch_c_file_paths(target_directory)
    
    # 取得したファイル群から関数定義および制御構造のネスト関係を抽出
    parsed_functions_list = extract_functions_from_files(c_file_list)
    
    # 抽出データを言語非依存の抽象辞書オブジェクト（IR）へ変換
    abstracted_project_data = generate_project_abstract_ir(parsed_functions_list)
    
    # 抽象化ノード間に関数ジャンプおよび復帰の参照リンクを付与
    abstracted_project_data = link_project_function_calls(abstracted_project_data)
    
    # 時系列に平坦化した実行スケジュール配列を生成（内部でログ出力関数をコール）
    scheduled_execution_list = generate_execution_schedule(abstracted_project_data)
    
    # 平坦化された時系列スケジュール構造からPlantUMLテキストファイルを1対1で機械的に生成
    execute_plantuml_translation(
        scheduled_execution_list,
        abstracted_project_data,
        output_file_path
    )

if __name__ == "__main__":
    main()
