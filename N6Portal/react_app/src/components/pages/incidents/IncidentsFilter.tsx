import { FC } from 'react';
import { useIntl } from 'react-intl';
import { format } from 'date-fns';
import FormSelect from 'components/forms/FormSelect';
import { TFilter, TFilterName } from 'components/pages/incidents/utils';
import DatePicker from 'components/forms/datePicker/DatePicker';
import FormTimeInput from 'components/forms/datePicker/TimeInput';
import { validateDatePicker } from 'components/forms/validation/validationSchema';
import FormFilterInput from 'components/forms/FormFilterInput';

interface IProps {
  filter: TFilter;
  removeFilter: (filterNames: TFilterName[]) => void;
}

const parseValue = (value: string) => {
  const removeWhitespaces = (v: string) => v.replaceAll(/\s+/g, '');
  const removeMultipleCommas = (v: string) => v.replace(/(,+)/g, ',');
  const removeLastComma = (v: string) => v.replace(/^(.+)(,)$/, (_, p1) => p1);
  const removeFirstComma = (v: string) => v.replace(/^(,)(.+)$/, (_, __, p2) => p2);
  return removeFirstComma(removeLastComma(removeMultipleCommas(removeWhitespaces(value))));
};

const IncidentsFilter: FC<IProps> = ({ filter, removeFilter }) => {
  const { messages } = useIntl();

  switch (filter.type) {
    case 'input':
      return (
        <div className="incidents-form-input-wrapper">
          <FormFilterInput
            name={filter.name}
            label={`${messages[filter.label]}`}
            validate={filter.validate}
            className="incidents-form-input"
            helperText="incidents_form_input_helper_text"
            customValueChange={parseValue}
          />
          <button
            aria-label={`${messages['incidents_remove_filter_ariaLabel']}${messages[filter.label]}`}
            className="incidents-form-input-btn"
            type="button"
            onClick={() => removeFilter([filter.name])}
          />
        </div>
      );
    case 'select':
      return (
        <div className="incidents-form-select-wrapper">
          <FormSelect
            name={filter.name}
            label={`${messages[filter.label]}`}
            options={filter.options}
            isMulti
            validate={filter.validate}
            placeholder=""
          />
          <button
            aria-label={`${messages['incidents_remove_filter_ariaLabel']}${messages[filter.label]}`}
            className="incidents-form-input-btn incidents-form-select-btn"
            type="button"
            onClick={() => removeFilter([filter.name])}
          />
        </div>
      );
    case 'date': {
      const currDate = new Date();
      return (
        <div className="incidents-form-input-date-wrapper">
          <DatePicker
            name={filter.name}
            label={`${messages[filter.label]}`}
            selectedDate={currDate}
            validate={validateDatePicker}
          />
          <div className="incidents-form-input-time-with-btn">
            <FormTimeInput
              name={filter.nameTime}
              label={`${messages[filter.labelTime]}`}
              validate={filter.validateTimeRequired}
              defaultValue={format(currDate, 'HH-mm')}
            />

            <button
              aria-label={`${messages['incidents_remove_filter_ariaLabel']}${messages[filter.label]}`}
              className="incidents-form-input-btn"
              type="button"
              onClick={() => removeFilter([filter.name, filter.nameTime])}
            />
          </div>
        </div>
      );
    }
    default:
      return null;
  }
};

export default IncidentsFilter;
