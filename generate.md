no1.

1base:
python3 tools/evaluation/pa11y_check.py generated/1/base.html    
Pa11y 检测目标：generated/1/base.html
标准：WCAG2AA
问题总数：35，错误：35，警告：0，提示：0

1. [error] WCAG2AA.Principle2.Guideline2_4.2_4_2.H25.1.NoTitleEl
   信息：A title should be provided for the document, using a non-empty title element in the head section.
   选择器：html > head
   片段：<head></head>

2. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #01aa72.
   选择器：#statsRow > div:nth-child(2) > span:nth-child(2)
   片段：<span class="stat-value">¥154,655.00</span>

3. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.15:1. Recommendation:  change text colour to #d18300.
   选择器：#statsRow > div:nth-child(3) > span:nth-child(2)
   片段：<span class="stat-value">5</span>

4. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#searchInput
   片段：<input type="text" id="searchInput" placeholder="搜索订单号、客户名称、商品...">

5. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#searchInput
   片段：<input type="text" id="searchInput" placeholder="搜索订单号、客户名称、商品...">

6. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Select.Name
   信息：This select element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#statusFilter
   片段：<select id="statusFilter">
                <option value=...</select>

7. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#statusFilter
   片段：<select id="statusFilter">
                <option value=...</select>

8. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change background to #4b6af3.
   选择器：#btnAdd
   片段：<button class="btn btn-add" id="btnAdd">＋ 新增订单</button>

9. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：html > body > div:nth-child(5) > div:nth-child(3) > div:nth-child(1) > table > thead > tr > th:nth-child(6)
   片段：<th data-field="date" style="width:120px;" class="sorted">下单日期 <span class="sort-arrow">↓...</th>

10. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：html > body > div:nth-child(5) > div:nth-child(3) > div:nth-child(1) > table > thead > tr > th:nth-child(6) > span
   片段：<span class="sort-arrow">↓</span>

11. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(1) > td:nth-child(1) > span
   片段：<span class="order-id">ORD-2024-0024</span>

12. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：#tableBody > tr:nth-child(1) > td:nth-child(7) > div > button:nth-child(1)
   片段：<button class="btn-sm btn-edit" data-id="ORD-2024-0024">✎ 编辑</button>

13. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.41:1. Recommendation:  change background to #fff5f5.
   选择器：#tableBody > tr:nth-child(1) > td:nth-child(7) > div > button:nth-child(2)
   片段：<button class="btn-sm btn-delete" data-id="ORD-2024-0024">✕ 删除</button>

14. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(2) > td:nth-child(1) > span
   片段：<span class="order-id">ORD-2024-0023</span>

15. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：#tableBody > tr:nth-child(2) > td:nth-child(7) > div > button:nth-child(1)
   片段：<button class="btn-sm btn-edit" data-id="ORD-2024-0023">✎ 编辑</button>

16. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.41:1. Recommendation:  change background to #fff5f5.
   选择器：#tableBody > tr:nth-child(2) > td:nth-child(7) > div > button:nth-child(2)
   片段：<button class="btn-sm btn-delete" data-id="ORD-2024-0023">✕ 删除</button>

17. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(3) > td:nth-child(1) > span
   片段：<span class="order-id">ORD-2024-0022</span>

18. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：#tableBody > tr:nth-child(3) > td:nth-child(7) > div > button:nth-child(1)
   片段：<button class="btn-sm btn-edit" data-id="ORD-2024-0022">✎ 编辑</button>

19. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.41:1. Recommendation:  change background to #fff5f5.
   选择器：#tableBody > tr:nth-child(3) > td:nth-child(7) > div > button:nth-child(2)
   片段：<button class="btn-sm btn-delete" data-id="ORD-2024-0022">✕ 删除</button>

20. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(4) > td:nth-child(1) > span
   片段：<span class="order-id">ORD-2024-0021</span>

21. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：#tableBody > tr:nth-child(4) > td:nth-child(7) > div > button:nth-child(1)
   片段：<button class="btn-sm btn-edit" data-id="ORD-2024-0021">✎ 编辑</button>

22. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.41:1. Recommendation:  change background to #fff5f5.
   选择器：#tableBody > tr:nth-child(4) > td:nth-child(7) > div > button:nth-child(2)
   片段：<button class="btn-sm btn-delete" data-id="ORD-2024-0021">✕ 删除</button>

23. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(5) > td:nth-child(1) > span
   片段：<span class="order-id">ORD-2024-0020</span>

24. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：#tableBody > tr:nth-child(5) > td:nth-child(7) > div > button:nth-child(1)
   片段：<button class="btn-sm btn-edit" data-id="ORD-2024-0020">✎ 编辑</button>

25. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.41:1. Recommendation:  change background to #fff5f5.
   选择器：#tableBody > tr:nth-child(5) > td:nth-child(7) > div > button:nth-child(2)
   片段：<button class="btn-sm btn-delete" data-id="ORD-2024-0020">✕ 删除</button>

26. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(6) > td:nth-child(1) > span
   片段：<span class="order-id">ORD-2024-0019</span>

27. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：#tableBody > tr:nth-child(6) > td:nth-child(7) > div > button:nth-child(1)
   片段：<button class="btn-sm btn-edit" data-id="ORD-2024-0019">✎ 编辑</button>

28. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.41:1. Recommendation:  change background to #fff5f5.
   选择器：#tableBody > tr:nth-child(6) > td:nth-child(7) > div > button:nth-child(2)
   片段：<button class="btn-sm btn-delete" data-id="ORD-2024-0019">✕ 删除</button>

29. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(7) > td:nth-child(1) > span
   片段：<span class="order-id">ORD-2024-0018</span>

30. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：#tableBody > tr:nth-child(7) > td:nth-child(7) > div > button:nth-child(1)
   片段：<button class="btn-sm btn-edit" data-id="ORD-2024-0018">✎ 编辑</button>

31. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.41:1. Recommendation:  change background to #fff5f5.
   选择器：#tableBody > tr:nth-child(7) > td:nth-child(7) > div > button:nth-child(2)
   片段：<button class="btn-sm btn-delete" data-id="ORD-2024-0018">✕ 删除</button>

32. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(8) > td:nth-child(1) > span
   片段：<span class="order-id">ORD-2024-0017</span>

33. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.83:1. Recommendation:  change text colour to #000107.
   选择器：#tableBody > tr:nth-child(8) > td:nth-child(7) > div > button:nth-child(1)
   片段：<button class="btn-sm btn-edit" data-id="ORD-2024-0017">✎ 编辑</button>

34. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.41:1. Recommendation:  change background to #fff5f5.
   选择器：#tableBody > tr:nth-child(8) > td:nth-child(7) > div > button:nth-child(2)
   片段：<button class="btn-sm btn-delete" data-id="ORD-2024-0017">✕ 删除</button>

35. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change background to #4b6af3.
   选择器：#pagination > button:nth-child(2)
   片段：<button class="active">1</button>

2rag:
python3 tools/generate.py "生成一个订单管理后台页面，包含搜索筛选、可排序表格、分页、编辑弹窗、toast提示。请只输出 完整 HTML/CSS/JS，不要 Markdown。" --limit 16 --save
提供商: deepseek  |  模型: deepseek-v4-pro  |  模式: rag  |  limit: 16
生成中...
第 1 轮 Pa11y 检测中...
Pa11y 检测结果: 0 errors, 0 warnings



no2.

2base:
python3 tools/evaluation/pa11y_check.py generated/2/base.html
Pa11y 检测目标：generated/2/base.html
标准：WCAG2AA
问题总数：38，错误：38，警告：0，提示：0

1. [error] WCAG2AA.Principle2.Guideline2_4.2_4_2.H25.1.NoTitleEl
   信息：A title should be provided for the document, using a non-empty title element in the head section.
   选择器：html > head
   片段：<head></head>

2. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 1.47:1. Recommendation:  change text colour to #313131.
   选择器：html > body > div:nth-child(6) > span:nth-child(2)
   片段：<span class="sep">›</span>

3. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 1.47:1. Recommendation:  change text colour to #313131.
   选择器：html > body > div:nth-child(6) > span:nth-child(4)
   片段：<span class="sep">›</span>

4. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 1.47:1. Recommendation:  change text colour to #313131.
   选择器：html > body > div:nth-child(6) > span:nth-child(6)
   片段：<span class="sep">›</span>

5. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.02:1. Recommendation:  change text colour to #434343.
   选择器：html > body > div:nth-child(7) > div > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="tag tag-hot">热销爆款</span>

6. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.63:1. Recommendation:  change text colour to #000504.
   选择器：html > body > div:nth-child(7) > div > div:nth-child(2) > div:nth-child(2) > span:nth-child(2)
   片段：<span class="tag tag-new">2024新款</span>

7. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.03:1. Recommendation:  change text colour to #050300.
   选择器：html > body > div:nth-child(7) > div > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="tag tag-best">好评如潮</span>

8. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.34:1. Recommendation:  change background to #474747.
   选择器：#displayDiscount
   片段：<span class="discount-tag" id="displayDiscount">-31%</span>

9. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.34:1. Recommendation:  change text colour to #474747.
   选择器：#selectedColorName
   片段：<span class="selected-spec-name" id="selectedColorName">曜石黑</span>

10. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.12:1. Recommendation:  change text colour to #444.
   选择器：#colorOptions > button:nth-child(1)
   片段：<button class="spec-btn active" data-color="black">曜石黑</button>

11. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.34:1. Recommendation:  change text colour to #474747.
   选择器：#selectedStorageName
   片段：<span class="selected-spec-name" id="selectedStorageName">128GB</span>

12. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.12:1. Recommendation:  change text colour to #444.
   选择器：#storageOptions > button:nth-child(1)
   片段：<button class="spec-btn active" data-storage="128">128GB</button>

13. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.89:1. Recommendation:  change text colour to #008765.
   选择器：#stockText
   片段：<span class="stock-text in-stock-color" id="stockText">库存充足（28件）</span>

14. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#maxHint
   片段：<span class="max-hint" id="maxHint">最多可购 <strong>28</strong> 件</span>

15. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#maxHint > strong
   片段：<strong>28</strong>

16. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.34:1. Recommendation:  change background to #474747.
   选择器：#btnAddCart
   片段：<button class="btn btn-add-cart" id="btnAddCart">
                        <svg w...</button>

17. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsSection > div:nth-child(1) > span
   片段：<span class="review-total">共 <strong>126</strong> 条评价</span>

18. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsSection > div:nth-child(1) > span > strong
   片段：<strong>126</strong>

19. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsSection > div:nth-child(2) > div:nth-child(1) > div > span
   片段：<span style="font-size:0.8rem;color:#999;">超出预期</span>

20. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsSection > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > span:nth-child(3)
   片段：<span class="bar-count">78</span>

21. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsSection > div:nth-child(2) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="bar-count">32</span>

22. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsSection > div:nth-child(2) > div:nth-child(2) > div:nth-child(3) > span:nth-child(3)
   片段：<span class="bar-count">10</span>

23. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsSection > div:nth-child(2) > div:nth-child(2) > div:nth-child(4) > span:nth-child(3)
   片段：<span class="bar-count">4</span>

24. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsSection > div:nth-child(2) > div:nth-child(2) > div:nth-child(5) > span:nth-child(3)
   片段：<span class="bar-count">2</span>

25. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.78:1. Recommendation:  change background to #d54141.
   选择器：#reviewsList > div:nth-child(1) > div:nth-child(1)
   片段：<div class="review-avatar" style="background:#ff6b6b;">王</div>

26. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.62:1. Recommendation:  change text colour to #252525.
   选择器：#reviewsList > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > span:nth-child(1)
   片段：<span class="review-spec-tag">曜石黑 / 256GB</span>

27. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsList > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > span:nth-child(2)
   片段：<span class="review-date">2024-12-15</span>

28. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 1.93:1. Recommendation:  change background to #06857c.
   选择器：#reviewsList > div:nth-child(2) > div:nth-child(1)
   片段：<div class="review-avatar" style="background:#4ecdc4;">杰</div>

29. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.62:1. Recommendation:  change text colour to #252525.
   选择器：#reviewsList > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > span:nth-child(1)
   片段：<span class="review-spec-tag">星空蓝 / 512GB</span>

30. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsList > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > span:nth-child(2)
   片段：<span class="review-date">2024-12-12</span>

31. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.43:1. Recommendation:  change background to #716acd.
   选择器：#reviewsList > div:nth-child(3) > div:nth-child(1)
   片段：<div class="review-avatar" style="background:#a29bfe;">李</div>

32. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.62:1. Recommendation:  change text colour to #252525.
   选择器：#reviewsList > div:nth-child(3) > div:nth-child(2) > div:nth-child(1) > span:nth-child(1)
   片段：<span class="review-spec-tag">陶瓷白 / 128GB</span>

33. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsList > div:nth-child(3) > div:nth-child(2) > div:nth-child(1) > span:nth-child(2)
   片段：<span class="review-date">2024-12-08</span>

34. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.48:1. Recommendation:  change background to #767676.
   选择器：#reviewsList > div:nth-child(4) > div:nth-child(1)
   片段：<div class="review-avatar" style="background:#fd79a8;">张</div>

35. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.62:1. Recommendation:  change text colour to #252525.
   选择器：#reviewsList > div:nth-child(4) > div:nth-child(2) > div:nth-child(1) > span:nth-child(1)
   片段：<span class="review-spec-tag">曜石黑 / 128GB</span>

36. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsList > div:nth-child(4) > div:nth-child(2) > div:nth-child(1) > span:nth-child(2)
   片段：<span class="review-date">2024-12-01</span>

37. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.62:1. Recommendation:  change text colour to #252525.
   选择器：#reviewsList > div:nth-child(5) > div:nth-child(2) > div:nth-child(1) > span:nth-child(1)
   片段：<span class="review-spec-tag">陶瓷白 / 256GB</span>

38. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.85:1. Recommendation:  change text colour to #767676.
   选择器：#reviewsList > div:nth-child(5) > div:nth-child(2) > div:nth-child(1) > span:nth-child(2)
   片段：<span class="review-date">2024-11-25</span>

2rag:
 python3 tools/generate.py "生成一个电商商品详情页面，包含商品图片轮播、规格选择、数量步进器、加入购物车按钮、收藏按钮、库存提示、评价区域。请只输出完整 HTML/CSS/JS，不要 Markdown。" --limit 16 --save       
提供商: deepseek  |  模型: deepseek-v4-pro  |  模式: rag  |  limit: 16
生成中...
第 1 轮 Pa11y 检测中...
Pa11y 检测结果: 33 errors, 0 warnings
修复中...
第 2 轮 Pa11y 检测中...
Pa11y 检测结果: 0 errors, 0 warnings

no3
3base:
python3 tools/evaluation/pa11y_check.py generated/3/base.html
Pa11y 检测目标：generated/3/base.html
标准：WCAG2AA
问题总数：46，错误：46，警告：0，提示：0

1. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.24:1. Recommendation:  change background to #917136.
   选择器：#roomTypeFilters > span:nth-child(1)
   片段：<span class="filter-tag active" data-type="all">全部房型</span>

2. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputNumber.Name
   信息：This numberinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#priceMinInput
   片段：<input type="number" id="priceMinInput" value="300" min="300" max="2000" step="50">

3. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#sidebar > div:nth-child(2) > div > div:nth-child(1) > span:nth-child(2)
   片段：<span>—</span>

4. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputNumber.Name
   信息：This numberinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#priceMaxInput
   片段：<input type="number" id="priceMaxInput" value="2000" min="300" max="2000" step="50">

5. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#sidebar > div:nth-child(2) > div > div:nth-child(1) > span:nth-child(4)
   片段：<span style="font-size:0.8rem;">/晚</span>

6. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputRange.Name
   信息：This rangeinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#priceMinSlider
   片段：<input type="range" id="priceMinSlider" min="300" max="2000" value="300" step="50">

7. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputRange.Name
   信息：This rangeinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#priceMaxSlider
   片段：<input type="range" id="priceMaxSlider" min="300" max="2000" value="2000" step="50">

8. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#sidebar > div:nth-child(2) > div > div:nth-child(3) > span:nth-child(1)
   片段：<span>¥300</span>

9. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#sidebar > div:nth-child(2) > div > div:nth-child(3) > span:nth-child(2)
   片段：<span>¥2000</span>

10. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.24:1. Recommendation:  change background to #917136.
   选择器：#bedTypeFilters > span:nth-child(1)
   片段：<span class="filter-tag active" data-bed="all">不限</span>

11. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputDate.Name
   信息：This dateinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#checkInDate
   片段：<input type="date" id="checkInDate" min="2026-06-09">

12. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputDate.Name
   信息：This dateinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#checkOutDate
   片段：<input type="date" id="checkOutDate" min="2026-06-10">

13. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Select.Name
   信息：This select element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#guestCount
   片段：<select class="guest-select" id="guestCount">
                        <optio...</select>

14. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#guestCount
   片段：<select class="guest-select" id="guestCount">
                        <optio...</select>

15. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.61:1. Recommendation:  change text colour to #120c00.
   选择器：#resultsCount > span
   片段：<span>6</span>

16. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Select.Name
   信息：This select element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#sortSelect
   片段：<select class="sort-select" id="sortSelect">
                    <option va...</select>

17. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#sortSelect
   片段：<select class="sort-select" id="sortSelect">
                    <option va...</select>

18. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(1) > div:nth-child(2) > div:nth-child(3)
   片段：<div class="room-desc">温馨舒适的标准客房，配备高品质床品，是商务出行和休闲旅游的理想...</div>

19. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.16:1. Recommendation:  change text colour to #ad6152.
   选择器：#roomList > div:nth-child(1) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(1)
   片段：<span class="room-price-currency">¥</span>

20. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(1) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(3)
   片段：<span class="room-price-unit">/晚</span>

21. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.43:1. Recommendation:  change text colour to #807560.
   选择器：#roomList > div:nth-child(1) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(4)
   片段：<span style="text-decoration:line-through;color:#b0a590;font-size:0.8rem;margin-left:6px;">¥488</span>

22. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(2) > div:nth-child(2) > div:nth-child(3)
   片段：<div class="room-desc">宽敞明亮的双床房，适合朋友结伴出行或商务伙伴同住，舒适实用。</div>

23. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.16:1. Recommendation:  change text colour to #ad6152.
   选择器：#roomList > div:nth-child(2) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(1)
   片段：<span class="room-price-currency">¥</span>

24. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(2) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(3)
   片段：<span class="room-price-unit">/晚</span>

25. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.43:1. Recommendation:  change text colour to #807560.
   选择器：#roomList > div:nth-child(2) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(4)
   片段：<span style="text-decoration:line-through;color:#b0a590;font-size:0.8rem;margin-left:6px;">¥528</span>

26. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(3) > div:nth-child(2) > div:nth-child(3)
   片段：<div class="room-desc">豪华大床房拥有绝佳海景视野，配备独立浴缸和高端洗浴用品，尽享奢...</div>

27. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.16:1. Recommendation:  change text colour to #ad6152.
   选择器：#roomList > div:nth-child(3) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(1)
   片段：<span class="room-price-currency">¥</span>

28. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(3) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(3)
   片段：<span class="room-price-unit">/晚</span>

29. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.43:1. Recommendation:  change text colour to #807560.
   选择器：#roomList > div:nth-child(3) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(4)
   片段：<span style="text-decoration:line-through;color:#b0a590;font-size:0.8rem;margin-left:6px;">¥888</span>

30. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(4) > div:nth-child(2) > div:nth-child(3)
   片段：<div class="room-desc">尊贵豪华套房，一室一厅格局，配备按摩浴缸和全景落地窗，享受顶级...</div>

31. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.16:1. Recommendation:  change text colour to #ad6152.
   选择器：#roomList > div:nth-child(4) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(1)
   片段：<span class="room-price-currency">¥</span>

32. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(4) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(3)
   片段：<span class="room-price-unit">/晚</span>

33. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.43:1. Recommendation:  change text colour to #807560.
   选择器：#roomList > div:nth-child(4) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(4)
   片段：<span style="text-decoration:line-through;color:#b0a590;font-size:0.8rem;margin-left:6px;">¥1688</span>

34. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(5) > div:nth-child(2) > div:nth-child(3)
   片段：<div class="room-desc">行政套房位于酒店顶层，拥有270度无敌海景，配备私人管家服务，...</div>

35. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.16:1. Recommendation:  change text colour to #ad6152.
   选择器：#roomList > div:nth-child(5) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(1)
   片段：<span class="room-price-currency">¥</span>

36. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(5) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(3)
   片段：<span class="room-price-unit">/晚</span>

37. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.43:1. Recommendation:  change text colour to #807560.
   选择器：#roomList > div:nth-child(5) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(4)
   片段：<span style="text-decoration:line-through;color:#b0a590;font-size:0.8rem;margin-left:6px;">¥2388</span>

38. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(6) > div:nth-child(2) > div:nth-child(3)
   片段：<div class="room-desc">专为家庭设计的亲子套房，设有儿童专属空间和丰富的亲子设施，让全...</div>

39. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.16:1. Recommendation:  change text colour to #ad6152.
   选择器：#roomList > div:nth-child(6) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(1)
   片段：<span class="room-price-currency">¥</span>

40. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.24:1. Recommendation:  change text colour to #827461.
   选择器：#roomList > div:nth-child(6) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(3)
   片段：<span class="room-price-unit">/晚</span>

41. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.43:1. Recommendation:  change text colour to #807560.
   选择器：#roomList > div:nth-child(6) > div:nth-child(2) > div:nth-child(4) > div > span:nth-child(4)
   片段：<span style="text-decoration:line-through;color:#b0a590;font-size:0.8rem;margin-left:6px;">¥1088</span>

42. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#guestName
   片段：<input type="text" id="guestName" placeholder="请输入您的姓名">

43. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#guestName
   片段：<input type="text" id="guestName" placeholder="请输入您的姓名">

44. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputTel.Name
   信息：This telinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#guestPhone
   片段：<input type="tel" id="guestPhone" placeholder="请输入手机号码">

45. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Textarea.Name
   信息：This textarea element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#guestNote
   片段：<textarea id="guestNote" placeholder="如有特殊需求请在此说明..."></textarea>

46. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#guestNote
   片段：<textarea id="guestNote" placeholder="如有特殊需求请在此说明..."></textarea>

   3rag:
   python3 tools/generate.py "生成一个酒店预订页面，包含日期选择、房型筛选、价格筛选、房间列表、预订弹窗、支付确认提示。请只输出完整 HTML/CSS/JS，不要 Markdown。" --limit 16  --save
提供商: deepseek  |  模型: deepseek-v4-pro  |  模式: rag  |  limit: 16
生成中...
第 1 轮 Pa11y 检测中...
Pa11y 检测结果: 15 errors, 0 warnings
修复中...
第 2 轮 Pa11y 检测中...
Pa11y 检测结果: 0 errors, 0 warnings

no4
4base:
python3 tools/evaluation/pa11y_check.py generated/4/base.html
Pa11y 检测目标：generated/4/base.html
标准：WCAG2AA
问题总数：125，错误：125，警告：0，提示：0

1. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.24:1. Recommendation:  change text colour to #205ee6.
   选择器：html > body > header > nav > ul > li:nth-child(1) > a
   片段：<a class="active">机票</a>

2. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#departure
   片段：<input type="text" id="departure" list="city-list-dep" placeholder="选择出发城市" value="北京" autocomplete="off">

3. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#departure
   片段：<input type="text" id="departure" list="city-list-dep" placeholder="选择出发城市" value="北京" autocomplete="off">

4. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#arrival
   片段：<input type="text" id="arrival" list="city-list-arr" placeholder="选择到达城市" value="上海" autocomplete="off">

5. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#arrival
   片段：<input type="text" id="arrival" list="city-list-arr" placeholder="选择到达城市" value="上海" autocomplete="off">

6. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputDate.Name
   信息：This dateinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#depDate
   片段：<input type="date" id="depDate" min="2026-06-09">

7. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputDate.Name
   信息：This dateinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#retDate
   片段：<input type="date" id="retDate" min="2026-06-09">

8. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change background to #c85200.
   选择器：#searchBtn
   片段：<button class="search-btn" id="searchBtn">🔍 搜索航班</button>

9. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputNumber.Name
   信息：This numberinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#priceMin
   片段：<input type="number" id="priceMin" placeholder="最低价" min="0" step="50" value="">

10. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#filtersSidebar > div:nth-child(2) > div:nth-child(2) > div > span
   片段：<span class="range-sep">—</span>

11. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputNumber.Name
   信息：This numberinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#priceMax
   片段：<input type="number" id="priceMax" placeholder="最高价" min="0" step="50" value="">

12. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#timeFilters > label:nth-child(1) > span
   片段：<span style="color:#9ca3af;font-size:0.75rem;">06:00-12:00</span>

13. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#timeFilters > label:nth-child(2) > span
   片段：<span style="color:#9ca3af;font-size:0.75rem;">12:00-18:00</span>

14. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#timeFilters > label:nth-child(3) > span
   片段：<span style="color:#9ca3af;font-size:0.75rem;">18:00-24:00</span>

15. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#airlineFilters > label:nth-child(1) > span
   片段：<span style="color:#9ca3af;font-size:0.7rem;">CA</span>

16. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#airlineFilters > label:nth-child(2) > span
   片段：<span style="color:#9ca3af;font-size:0.7rem;">MU</span>

17. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#airlineFilters > label:nth-child(3) > span
   片段：<span style="color:#9ca3af;font-size:0.7rem;">CZ</span>

18. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#airlineFilters > label:nth-child(4) > span
   片段：<span style="color:#9ca3af;font-size:0.7rem;">HU</span>

19. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#airlineFilters > label:nth-child(5) > span
   片段：<span style="color:#9ca3af;font-size:0.7rem;">9C</span>

20. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#airlineFilters > label:nth-child(6) > span
   片段：<span style="color:#9ca3af;font-size:0.7rem;">HO</span>

21. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#airlineFilters > label:nth-child(7) > span
   片段：<span style="color:#9ca3af;font-size:0.7rem;">ZH</span>

22. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#airlineFilters > label:nth-child(8) > span
   片段：<span style="color:#9ca3af;font-size:0.7rem;">MF</span>

23. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.24:1. Recommendation:  change text colour to #205ee6.
   选择器：#resultCount
   片段：<span class="count-num" id="resultCount">17</span>

24. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">CZ3270</div>

25. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时6分钟</span>

26. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

27. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(1) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>751</div>

28. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(1) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

29. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(1) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A330 · 直飞</div>

30. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(2) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">MU7806</div>

31. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(2) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时5分钟</span>

32. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(2) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

33. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(2) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>776</div>

34. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(2) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

35. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(2) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A350 · 直飞</div>

36. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(3) > div:nth-child(2) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">CZ4164</div>

37. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(3) > div:nth-child(3) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">2小时46分钟</span>

38. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(3) > div:nth-child(3) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

39. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(3) > div:nth-child(4) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>848</div>

40. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(3) > div:nth-child(4) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

41. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(3) > div:nth-child(4) > div:nth-child(2)
   片段：<div class="price-note">波音787 · 直飞</div>

42. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(4) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">HU5929</div>

43. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(4) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时46分钟</span>

44. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(4) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

45. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(4) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>872</div>

46. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(4) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

47. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(4) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A330 · 直飞</div>

48. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(5) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">HU2097</div>

49. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(5) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">1小时48分钟</span>

50. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(5) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

51. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(5) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>878</div>

52. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(5) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

53. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(5) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A320 · 直飞</div>

54. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(6) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">9C8627</div>

55. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(6) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时32分钟</span>

56. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(6) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

57. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(6) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>904</div>

58. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(6) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

59. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(6) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">波音737 · 直飞</div>

60. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(7) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">CA6641</div>

61. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(7) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">1小时51分钟</span>

62. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(7) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

63. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(7) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>978</div>

64. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(7) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

65. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(7) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">波音787 · 直飞</div>

66. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(8) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">HO1107</div>

67. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(8) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时19分钟</span>

68. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.07:1. Recommendation:  change text colour to #060400.
   选择器：#flightList > div:nth-child(8) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="stop-info">经停武汉 (2站)</span>

69. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(8) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>987</div>

70. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(8) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

71. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(8) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A350 · 中转</div>

72. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(9) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">9C6395</div>

73. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(9) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">2小时59分钟</span>

74. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.07:1. Recommendation:  change text colour to #060400.
   选择器：#flightList > div:nth-child(9) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="stop-info">经停济南 (1站)</span>

75. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(9) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>991</div>

76. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(9) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

77. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(9) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">波音787 · 中转</div>

78. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(10) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">HO5176</div>

79. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(10) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时58分钟</span>

80. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.07:1. Recommendation:  change text colour to #060400.
   选择器：#flightList > div:nth-child(10) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="stop-info">经停石家庄 (1站)</span>

81. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(10) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>1,007</div>

82. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(10) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

83. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(10) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A330 · 中转</div>

84. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(11) > div:nth-child(2) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">HU5091</div>

85. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(11) > div:nth-child(3) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">1小时47分钟</span>

86. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(11) > div:nth-child(3) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

87. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(11) > div:nth-child(4) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>1,024</div>

88. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(11) > div:nth-child(4) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

89. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(11) > div:nth-child(4) > div:nth-child(2)
   片段：<div class="price-note">波音737 · 直飞</div>

90. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(12) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">9C6985</div>

91. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(12) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时56分钟</span>

92. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(12) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

93. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(12) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>1,024</div>

94. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(12) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

95. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(12) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A330 · 直飞</div>

96. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(13) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">HO5125</div>

97. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(13) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">2小时21分钟</span>

98. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(13) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

99. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(13) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>1,048</div>

100. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(13) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

101. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(13) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A350 · 直飞</div>

102. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(14) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">HO1323</div>

103. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(14) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">2小时2分钟</span>

104. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(14) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

105. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(14) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>1,051</div>

106. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(14) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

107. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(14) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A320 · 直飞</div>

108. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(15) > div:nth-child(2) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">ZH7517</div>

109. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(15) > div:nth-child(3) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">1小时47分钟</span>

110. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(15) > div:nth-child(3) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

111. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(15) > div:nth-child(4) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>1,057</div>

112. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(15) > div:nth-child(4) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

113. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(15) > div:nth-child(4) > div:nth-child(2)
   片段：<div class="price-note">波音737 · 直飞</div>

114. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(16) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">ZH7742</div>

115. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(16) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时20分钟</span>

116. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(16) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

117. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(16) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>1,066</div>

118. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(16) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

119. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(16) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A320 · 直飞</div>

120. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(17) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2)
   片段：<div class="flight-no">HO6399</div>

121. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(17) > div:nth-child(2) > div:nth-child(2) > span:nth-child(1)
   片段：<span class="duration">3小时4分钟</span>

122. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#flightList > div:nth-child(17) > div:nth-child(2) > div:nth-child(2) > span:nth-child(3)
   片段：<span class="direct-tag">直飞</span>

123. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G145.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 3:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #f26c0f.
   选择器：#flightList > div:nth-child(17) > div:nth-child(3) > div:nth-child(1)
   片段：<div class="price"><span class="yen">¥</span>1,136</div>

124. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.8:1. Recommendation:  change text colour to #c85200.
   选择器：#flightList > div:nth-child(17) > div:nth-child(3) > div:nth-child(1) > span
   片段：<span class="yen">¥</span>

125. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#flightList > div:nth-child(17) > div:nth-child(3) > div:nth-child(2)
   片段：<div class="price-note">空客A350 · 直飞</div>

   4rag
   python3 tools/generate.py "生成一个机票搜索页面，包含出发地到达地输入、日期选择、乘客数量选择、航班筛选、排序、结果列表。请只输出完整 HTML/CSS/JS，不要 Markdown。" --limit 16  --save
提供商: deepseek  |  模型: deepseek-v4-pro  |  模式: rag  |  limit: 16
生成中...
第 1 轮 Pa11y 检测中...
Pa11y 检测结果: 8 errors, 0 warnings
修复中...
第 2 轮 Pa11y 检测中...
Pa11y 检测结果: 0 errors, 0 warnings

no5:
5base:
python3 tools/evaluation/pa11y_check.py generated/5/base.html
Pa11y 检测目标：generated/5/base.html
标准：WCAG2AA
问题总数：34，错误：34，警告：0，提示：0

1. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.9:1. Recommendation:  change text colour to #616876.
   选择器：#step2 > span
   片段：<span class="step-num">2</span>

2. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.9:1. Recommendation:  change text colour to #616876.
   选择器：#step3 > span
   片段：<span class="step-num">3</span>

3. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.9:1. Recommendation:  change text colour to #616876.
   选择器：#step4 > span
   片段：<span class="step-num">4</span>

4. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(2) > span:nth-child(3)
   片段：<span class="dept-count">3位医生</span>

5. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(3) > span:nth-child(3)
   片段：<span class="dept-count">3位医生</span>

6. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(4) > span:nth-child(3)
   片段：<span class="dept-count">3位医生</span>

7. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(5) > span:nth-child(3)
   片段：<span class="dept-count">3位医生</span>

8. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(6) > span:nth-child(3)
   片段：<span class="dept-count">2位医生</span>

9. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(7) > span:nth-child(3)
   片段：<span class="dept-count">3位医生</span>

10. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(8) > span:nth-child(3)
   片段：<span class="dept-count">2位医生</span>

11. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(9) > span:nth-child(3)
   片段：<span class="dept-count">2位医生</span>

12. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.39:1. Recommendation:  change background to #f6f7f9.
   选择器：#departmentGrid > button:nth-child(10) > span:nth-child(3)
   片段：<span class="dept-count">3位医生</span>

13. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.32:1. Recommendation:  change text colour to #000201.
   选择器：#doctorList > div:nth-child(1) > span
   片段：<span class="doctor-badge ">余12号</span>

14. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.32:1. Recommendation:  change text colour to #000201.
   选择器：#doctorList > div:nth-child(2) > span
   片段：<span class="doctor-badge ">余8号</span>

15. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.32:1. Recommendation:  change text colour to #000201.
   选择器：#doctorList > div:nth-child(3) > span
   片段：<span class="doctor-badge ">余15号</span>

16. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.24:1. Recommendation:  change text colour to #000201.
   选择器：html > body > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1)
   片段：<div class="card-icon green">📅</div>

17. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.33:1. Recommendation:  change background to #f0f8ff.
   选择器：#dateScroll > div:nth-child(1) > span:nth-child(3)
   片段：<span class="day-month">6月</span>

18. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#morningSlots > div
   片段：<div style="grid-column:1/-1;text-align:center;color:var(--gray-400);padding:16px;font-size:0.85rem;">请先选择医生和日期</div>

19. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.54:1. Recommendation:  change text colour to #707783.
   选择器：#afternoonSlots > div
   片段：<div style="grid-column:1/-1;text-align:center;color:var(--gray-400);padding:16px;font-size:0.85rem;">请先选择医生和日期</div>

20. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.43:1. Recommendation:  change text colour to #181f2b.
   选择器：#timeSummary > span
   片段：<span class="summary-empty">请选择日期和时间段</span>

21. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.86:1. Recommendation:  change text colour to #020100.
   选择器：html > body > div:nth-child(2) > div:nth-child(2) > div:nth-child(2) > div > div:nth-child(1)
   片段：<div class="card-icon orange">📋</div>

22. [error] WCAG2AA.Principle3.Guideline3_2.3_2_2.H32.2
   信息：This form does not contain a submit button, which creates issues for those who cannot submit the form using the keyboard. Submit buttons are INPUT elements with type attribute "submit" or "image", or BUTTON elements with type "submit" or omitted/invalid.
   选择器：#patientForm
   片段：<form id="patientForm" novalidate="">
                    <div class...</form>

23. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.76:1. Recommendation:  change text colour to #de3333.
   选择器：#patientForm > div:nth-child(1) > div:nth-child(1) > label > span
   片段：<span class="required">*</span>

24. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#patientName
   片段：<input type="text" class="form-input" id="patientName" placeholder="请输入患者姓名" maxlength="20">

25. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#patientName
   片段：<input type="text" class="form-input" id="patientName" placeholder="请输入患者姓名" maxlength="20">

26. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.76:1. Recommendation:  change text colour to #de3333.
   选择器：#patientForm > div:nth-child(1) > div:nth-child(2) > label > span
   片段：<span class="required">*</span>

27. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputTel.Name
   信息：This telinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#patientPhone
   片段：<input type="tel" class="form-input" id="patientPhone" placeholder="请输入手机号码" maxlength="11">

28. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.76:1. Recommendation:  change text colour to #de3333.
   选择器：#patientForm > div:nth-child(2) > div:nth-child(1) > label > span
   片段：<span class="required">*</span>

29. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#patientIdCard
   片段：<input type="text" class="form-input" id="patientIdCard" placeholder="请输入身份证号" maxlength="18">

30. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#patientIdCard
   片段：<input type="text" class="form-input" id="patientIdCard" placeholder="请输入身份证号" maxlength="18">

31. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.76:1. Recommendation:  change text colour to #de3333.
   选择器：#patientForm > div:nth-child(2) > div:nth-child(2) > label > span
   片段：<span class="required">*</span>

32. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputNumber.Name
   信息：This numberinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#patientAge
   片段：<input type="number" class="form-input" id="patientAge" placeholder="年龄" min="0" max="150">

33. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Textarea.Name
   信息：This textarea element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#patientSymptom
   片段：<textarea class="form-textarea" id="patientSymptom" placeholder="请简要描述您的症状（可选）" maxlength="300"></textarea>

34. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#patientSymptom
   片段：<textarea class="form-textarea" id="patientSymptom" placeholder="请简要描述您的症状（可选）" maxlength="300"></textarea>

   5rag:
   python3 tools/generate.py "生成一个医院预约挂号页面，包含科室选择、医生筛选、日期时间段选择、患者信息表单、确认预约弹窗。请只输出完整 HTML/CSS/JS，不要 Markdown。" --limit 16 --save 
提供商: deepseek  |  模型: deepseek-v4-pro  |  模式: rag  |  limit: 16
生成中...
第 1 轮 Pa11y 检测中...
Pa11y 检测结果: 11 errors, 0 warnings
修复中...
第 2 轮 Pa11y 检测中...
Pa11y 检测结果: 0 errors, 0 warnings

no6:
6base:
python3 tools/evaluation/pa11y_check.py generated/6/base.html
Pa11y 检测目标：generated/6/base.html
标准：WCAG2AA
问题总数：10，错误：10，警告：0，提示：0

1. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#recipientName
   片段：<input type="text" class="form-input" id="recipientName" placeholder="请输入收款人姓名" maxlength="30" autocomplete="off">

2. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#recipientName
   片段：<input type="text" class="form-input" id="recipientName" placeholder="请输入收款人姓名" maxlength="30" autocomplete="off">

3. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#recipientAccount
   片段：<input type="text" class="form-input" id="recipientAccount" placeholder="请输入银行卡号" maxlength="19" autocomplete="off" inputmode="numeric">

4. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#recipientAccount
   片段：<input type="text" class="form-input" id="recipientAccount" placeholder="请输入银行卡号" maxlength="19" autocomplete="off" inputmode="numeric">

5. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Select.Name
   信息：This select element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#recipientBank
   片段：<select class="form-select" id="recipientBank">
                    <option va...</select>

6. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#recipientBank
   片段：<select class="form-select" id="recipientBank">
                    <option va...</select>

7. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#amount
   片段：<input type="text" class="form-input" id="amount" placeholder="0.00" maxlength="14" autocomplete="off" inputmode="decimal">

8. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#amount
   片段：<input type="text" class="form-input" id="amount" placeholder="0.00" maxlength="14" autocomplete="off" inputmode="decimal">

9. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#remark
   片段：<input type="text" class="form-input" id="remark" placeholder="添加备注信息" maxlength="50" autocomplete="off">

10. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#remark
   片段：<input type="text" class="form-input" id="remark" placeholder="添加备注信息" maxlength="50" autocomplete="off">

   6rag:
   python3 tools/generate.py "生成一个银行转账页面，包含收款人信息表单、金额输入、用途选择、二次确认弹窗、转账结果提示。请只输出完整 HTML/CSS/JS，不要 Markdown。" --limit 16  --save
提供商: deepseek  |  模型: deepseek-v4-pro  |  模式: rag  |  limit: 16
生成中...
第 1 轮 Pa11y 检测中...
Pa11y 检测结果: 0 errors, 0 warnings

no7:
7base:
 python3 tools/evaluation/pa11y_check.py generated/7/base.html
Pa11y 检测目标：generated/7/base.html
标准：WCAG2AA
问题总数：40，错误：40，警告：0，提示：0

1. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change background to #4b6af3.
   选择器：html > body > div:nth-child(2) > div:nth-child(1) > button
   片段：<button class="btn btn-primary" onclick="openCreateModal()">
                <span>＋</span>...</button>

2. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change background to #4b6af3.
   选择器：html > body > div:nth-child(2) > div:nth-child(1) > button > span
   片段：<span>＋</span>

3. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.99:1. Recommendation:  change text colour to #000007.
   选择器：#statsRow > div:nth-child(1) > div:nth-child(2)
   片段：<div class="stat-icon">📊</div>

4. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.41:1. Recommendation:  change text colour to #000504.
   选择器：#statsRow > div:nth-child(2) > div:nth-child(2)
   片段：<div class="stat-icon">✅</div>

5. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.07:1. Recommendation:  change text colour to #060400.
   选择器：#statsRow > div:nth-child(3) > div:nth-child(2)
   片段：<div class="stat-icon">⏳</div>

6. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.44:1. Recommendation:  change text colour to #0a0000.
   选择器：#statsRow > div:nth-child(4) > div:nth-child(2)
   片段：<div class="stat-icon">🚫</div>

7. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#searchInput
   片段：<input type="text" id="searchInput" placeholder="搜索发票号、客户名称、开票内容..." oninput="handleSearch()">

8. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#searchInput
   片段：<input type="text" id="searchInput" placeholder="搜索发票号、客户名称、开票内容..." oninput="handleSearch()">

9. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Select.Name
   信息：This select element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#statusFilter
   片段：<select class="filter-select" id="statusFilter" onchange="handleFilter()">
                <option value=...</select>

10. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#statusFilter
   片段：<select class="filter-select" id="statusFilter" onchange="handleFilter()">
                <option value=...</select>

11. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.13:1. Recommendation:  change text colour to #000b3d.
   选择器：html > body > div:nth-child(2) > div:nth-child(4) > div:nth-child(1) > table > thead > tr > th:nth-child(1) > span
   片段：<span class="sort-arrow">▼</span>

12. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.45:1. Recommendation:  change text colour to #181f2b.
   选择器：html > body > div:nth-child(2) > div:nth-child(4) > div:nth-child(1) > table > thead > tr > th:nth-child(2) > span
   片段：<span class="sort-arrow">▼</span>

13. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.45:1. Recommendation:  change text colour to #181f2b.
   选择器：html > body > div:nth-child(2) > div:nth-child(4) > div:nth-child(1) > table > thead > tr > th:nth-child(3) > span
   片段：<span class="sort-arrow">▼</span>

14. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.45:1. Recommendation:  change text colour to #181f2b.
   选择器：html > body > div:nth-child(2) > div:nth-child(4) > div:nth-child(1) > table > thead > tr > th:nth-child(4) > span
   片段：<span class="sort-arrow">▼</span>

15. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.45:1. Recommendation:  change text colour to #181f2b.
   选择器：html > body > div:nth-child(2) > div:nth-child(4) > div:nth-child(1) > table > thead > tr > th:nth-child(5) > span
   片段：<span class="sort-arrow">▼</span>

16. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 2.45:1. Recommendation:  change text colour to #181f2b.
   选择器：html > body > div:nth-child(2) > div:nth-child(4) > div:nth-child(1) > table > thead > tr > th:nth-child(6) > span
   片段：<span class="sort-arrow">▼</span>

17. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(1) > td:nth-child(1) > span
   片段：<span class="invoice-id">INV-2024-0015</span>

18. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(2) > td:nth-child(1) > span
   片段：<span class="invoice-id">INV-2024-0014</span>

19. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.58:1. Recommendation:  change text colour to #000403.
   选择器：#tableBody > tr:nth-child(2) > td:nth-child(6) > span
   片段：<span class="status-badge status-issued"><span class="dot"></span>已开票</span>

20. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(3) > td:nth-child(1) > span
   片段：<span class="invoice-id">INV-2024-0013</span>

21. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(4) > td:nth-child(1) > span
   片段：<span class="invoice-id">INV-2024-0012</span>

22. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.58:1. Recommendation:  change text colour to #000403.
   选择器：#tableBody > tr:nth-child(4) > td:nth-child(6) > span
   片段：<span class="status-badge status-issued"><span class="dot"></span>已开票</span>

23. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(5) > td:nth-child(1) > span
   片段：<span class="invoice-id">INV-2024-0011</span>

24. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(6) > td:nth-child(1) > span
   片段：<span class="invoice-id">INV-2024-0010</span>

25. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.58:1. Recommendation:  change text colour to #000403.
   选择器：#tableBody > tr:nth-child(6) > td:nth-child(6) > span
   片段：<span class="status-badge status-issued"><span class="dot"></span>已开票</span>

26. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(7) > td:nth-child(1) > span
   片段：<span class="invoice-id">INV-2024-0009</span>

27. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change text colour to #4b6af3.
   选择器：#tableBody > tr:nth-child(8) > td:nth-child(1) > span
   片段：<span class="invoice-id">INV-2024-0008</span>

28. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 3.58:1. Recommendation:  change text colour to #000403.
   选择器：#tableBody > tr:nth-child(8) > td:nth-child(6) > span
   片段：<span class="status-badge status-issued"><span class="dot"></span>已开票</span>

29. [error] WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail
   信息：This element has insufficient contrast at this conformance level. Expected a contrast ratio of at least 4.5:1, but text in this element has a contrast ratio of 4.28:1. Recommendation:  change background to #4b6af3.
   选择器：#paginationBtns > button:nth-child(2)
   片段：<button class="active" onclick="goToPage(1)">1</button>

30. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#formCustomer
   片段：<input type="text" id="formCustomer" placeholder="请输入客户名称" required="">

31. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#formCustomer
   片段：<input type="text" id="formCustomer" placeholder="请输入客户名称" required="">

32. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#formTaxId
   片段：<input type="text" id="formTaxId" placeholder="请输入客户税号">

33. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#formTaxId
   片段：<input type="text" id="formTaxId" placeholder="请输入客户税号">

34. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name
   信息：This textinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#formContent
   片段：<input type="text" id="formContent" placeholder="请输入开票内容，如：技术服务费" required="">

35. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#formContent
   片段：<input type="text" id="formContent" placeholder="请输入开票内容，如：技术服务费" required="">

36. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputNumber.Name
   信息：This numberinput element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#formAmount
   片段：<input type="number" id="formAmount" placeholder="请输入金额" step="0.01" min="0.01" required="">

37. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Select.Name
   信息：This select element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#formTaxRate
   片段：<select id="formTaxRate">
                              ...</select>

38. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#formTaxRate
   片段：<select id="formTaxRate">
                              ...</select>

39. [error] WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.Textarea.Name
   信息：This textarea element does not have a name available to an accessibility API. Valid names are: label element, title , aria-label , aria-labelledby .
   选择器：#formRemark
   片段：<textarea id="formRemark" placeholder="可选：填写备注信息"></textarea>

40. [error] WCAG2AA.Principle1.Guideline1_3.1_3_1.F68
   信息：This form field should be labelled in some way. Use the label element (either with a "for" attribute or wrapped around the form field), or "title", "aria-label" or "aria-labelledby" attributes as appropriate.
   选择器：#formRemark
   片段：<textarea id="formRemark" placeholder="可选：填写备注信息"></textarea>