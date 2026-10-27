"""Prepare inline clipboard content through the existing text ownership path."""

from .models.rich_document import FactFieldSpan,Hyperlink,InlineStyles
from .models.template_authoring import ReplaceText
from .models.template_document import BoundLink,ManualScopeSpan,PresentedHyperlink,PresentedText
from .rich_mutations import cut_inline,inline_text
from .template_authoring import allocate_classified_inline
from .template_clipboard import selected_witnesses
from .template_clipboard_witnesses import verify_witnesses


def literal_content(content):
    def text(part):
        return PresentedText(type='text',text=part.text,styles=part.styles.model_copy(deep=True))
    return [PresentedHyperlink(type='link',href=part.href,content=[text(child) for child in part.content])
        if isinstance(part,Hyperlink) else text(part) for part in content]


def retained_payload(response,operation,clipboard,kind):
    if (clipboard is None or clipboard.capture.project_id!=response.workspace.project_id
            or clipboard.capture.clipboard_capture_id!=operation.source.clipboard_capture_id
            or clipboard.payload.kind!=kind):
        raise ValueError('paste requires its matching retained capture kind')
    project=response.workspace.project
    verify_witnesses(project,clipboard.witnesses,clipboard.package_fingerprint)
    if selected_witnesses(project,clipboard.payload)!=clipboard.witnesses:
        raise ValueError('clipboard witness coverage changed')
    return clipboard.payload


def source_content(response,operation,clipboard):
    if operation.source.kind=='literal':return literal_content(operation.source.content)
    return [part.model_copy(deep=True) for part in retained_payload(response,operation,clipboard,'inline').content]


class InlineReplacement:
    def __init__(self,content):
        self.content=content
        self.semantic=any(isinstance(part,(FactFieldSpan,ManualScopeSpan,BoundLink)) for part in content)
        self.allocator=None
        self.same_text=False

    def guard(self,content,selected,fields,scope_ranges,bound):
        from .template_preparation import _leaves,_length
        owned=bool(fields or scope_ranges or bound is not None)
        if self.semantic and owned:
            raise ValueError('semantic paste cannot overlay destination field or scope authority')
        linked=any(isinstance(part,(Hyperlink,BoundLink)) for part in self.content)
        if linked and owned:
            raise ValueError('linked paste cannot be represented inside a destination field or scope')
        cursor=0
        for part in content:
            length=_length(part)
            overlap=selected.start<cursor+length and selected.end>cursor
            nested=(selected.start!=selected.end and cursor<=selected.start<=selected.end<=cursor+length
                or selected.start==selected.end and cursor<selected.start<cursor+length
                or selected.start==selected.end and bound is not None and any(
                    leaf is bound for leaf,_start,_end in _leaves([part])))
            if isinstance(part,BoundLink) and self.semantic and overlap:
                raise ValueError('semantic paste touches destination link authority')
            if isinstance(part,(Hyperlink,BoundLink)) and nested and (self.semantic or linked):
                raise ValueError('nested clipboard links or semantic link children are unsupported')
            cursor+=length
        self.evidence=[];self.reference=getattr(bound,'presentation',None)
        for part,start,end in _leaves(content):
            if start<selected.end and end>selected.start or part is bound:
                self.reference=self.reference or getattr(part,'presentation',None)
                for citation in getattr(part,'citations',[]):
                    if citation not in self.evidence:self.evidence.append(citation.model_copy(deep=True))

    def overlay(self,content,selected,path):
        from .template_preparation import _length
        selected_parts=cut_inline(content,selected.start,selected.end,id_factory=self.allocator,
            allocation_path=(*path,'paste-overlay'))
        runs=[];cursor=0
        for part in self.content:
            length=_length(part);runs.append((part,cursor,cursor+length));cursor+=length
        def visit(parts,origin,slot):
            result=[];cursor=origin
            for index,part in enumerate(parts):
                length=_length(part)
                if isinstance(part,(Hyperlink,BoundLink)):
                    copied=part.model_copy(deep=True);copied.content=visit(part.content,cursor,(*slot,index))
                    result.append(copied)
                elif length==0:
                    result.append(part.model_copy(deep=True))
                else:
                    for run_index,(run,start,end) in enumerate(runs):
                        left,right=max(cursor,start),min(cursor+length,end)
                        if left>=right:continue
                        fragment=cut_inline([part],left-cursor,right-cursor,id_factory=self.allocator,
                            allocation_path=(*slot,index,'paste-run',run_index))[0]
                        fragment.styles=run.styles.model_copy(deep=True)
                        if run.presentation is not None:fragment.presentation=run.presentation.model_copy(deep=True)
                        for citation in run.citations:
                            if citation not in fragment.citations:fragment.citations.append(citation.model_copy(deep=True))
                        result.append(fragment)
                cursor+=length
            return result
        return visit(selected_parts,0,(*path,'paste-overlay-runs'))

    def insert(self,bound,path,content,selected):
        if self.same_text and not any(isinstance(part,Hyperlink) for part in self.content):
            return self.overlay(content,selected,path)
        parts=[part.model_copy(deep=True) for part in self.content]
        if self.semantic:return allocate_classified_inline(parts,id_factory=self.allocator)
        if not parts and isinstance(bound,(FactFieldSpan,ManualScopeSpan)):
            parts=[PresentedText(type='text',text='',styles=InlineStyles())]
        result=[]
        for index,part in enumerate(parts):
            if isinstance(bound,(FactFieldSpan,ManualScopeSpan)):
                inserted=bound.model_copy(deep=True)
                inserted.text,inserted.styles=part.text,part.styles.model_copy(deep=True)
                inserted.presentation=part.presentation or bound.presentation
                inserted.citations=[value.model_copy(deep=True) for value in getattr(bound,'citations',[])]
                for citation in [*self.evidence,*part.citations]:
                    if citation not in inserted.citations:inserted.citations.append(citation.model_copy(deep=True))
                if isinstance(bound,ManualScopeSpan):
                    inserted.fragment_id=self.allocator.allocate('manual-fragment',
                        ['paste-scope-fragment',bound.fragment_id,list(path),index])
                else:
                    inserted.binding_id=self.allocator.allocate('fragment',
                        ['paste-field-fragment',bound.binding_id,list(path),index])
                result.append(inserted)
            else:
                if part.presentation is None:part.presentation=self.reference
                for child in part.content if isinstance(part,Hyperlink) else [part]:
                    for citation in self.evidence:
                        if citation not in child.citations:child.citations.append(citation.model_copy(deep=True))
                result.append(part)
        return result


def prepare_inline_paste(response,request,*,clipboard=None,occupied=None):
    from .template_preparation import prepare_text_edit
    operation=request.operations[0]
    content=source_content(response,operation,clipboard)
    replacement=InlineReplacement(content)
    text=''.join(inline_text(part) for part in content)
    command=ReplaceText(kind='replace_text',opId=operation.op_id,range=operation.destination,text=text,styles={})
    return prepare_text_edit(response,request,operation=command,replacement=replacement,occupied=occupied)
